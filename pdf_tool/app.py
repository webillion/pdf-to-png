import os
import sqlite3
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, jsonify, g, send_from_directory

# --- 設定エリア ---
# 画像表示のために static_folder='static' は必須です
app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.urandom(24)

# パスワード設定
VIP_PASSWORD = os.environ.get("VIP_PASSWORD", "secret_password")

# 1日の利用上限回数（3回まではOK、4回目でブロック）
DAILY_LIMIT = 3

# データベースファイルの場所
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'usage.db')

# --- 日本時間（JST）の設定 ---
# サーバーの時間を日本時間に合わせます（これがないと朝にリセットされません）
JST = timezone(timedelta(hours=9), 'JST')

def get_today_str():
    """日本時間で今日の日付を取得"""
    return datetime.now(JST).strftime('%Y-%m-%d')

def get_db():
    """データベース接続"""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    """データベース初期化"""
    with app.app_context():
        db = get_db()
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                ip TEXT PRIMARY KEY,
                last_date TEXT,
                count INTEGER,
                is_vip INTEGER
            )
        ''')
        db.commit()

# アプリ起動時にDBを作成
init_db()

def get_remote_ip():
    """ユーザーのIPアドレスを取得"""
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0].split(',')[0].strip()
    return request.remote_addr

def get_user_status(ip):
    """ユーザーの現在の回数とVIP状態を取得（日付変更ならリセット）"""
    today_str = get_today_str()
    db = get_db()
    
    cursor = db.execute('SELECT * FROM users WHERE ip = ?', (ip,))
    user = cursor.fetchone()
    
    # 初回ユーザーの場合
    if user is None:
        db.execute('INSERT INTO users (ip, last_date, count, is_vip) VALUES (?, ?, ?, ?)', 
                   (ip, today_str, 0, 0))
        db.commit()
        return {'count': 0, 'is_vip': False}
    
    # 日付が変わっていたらリセット（VIP状態は維持）
    if user['last_date'] != today_str:
        is_vip = user['is_vip']
        db.execute('UPDATE users SET last_date = ?, count = 0 WHERE ip = ?', (today_str, ip))
        db.commit()
        return {'count': 0, 'is_vip': bool(is_vip)}
    
    return {'count': user['count'], 'is_vip': bool(user['is_vip'])}

# --- ルーティング ---

@app.route('/')
def index():
    return render_template('index.html')

# X（Twitter）などのOGP画像用
@app.route('/static/og-image.png')
def send_og_image_static():
    return send_from_directory('static', 'og-image.png')

# 念のためルート直下のアクセスもカバー
@app.route('/og-image.png')
def send_og_image_root():
    return send_from_directory('static', 'og-image.png')

@app.route('/api/status', methods=['GET'])
def check_status():
    """現在の利用状況を返す"""
    ip = get_remote_ip()
    status = get_user_status(ip)
    return jsonify(status)

@app.route('/api/unlock', methods=['POST'])
def unlock_limit():
    """パスワード認証で無制限モードへ"""
    ip = get_remote_ip()
    data = request.get_json() or {}
    password = data.get('password', '')
    
    if password == VIP_PASSWORD:
        db = get_db()
        # is_vip を 1 (True) に書き換え
        db.execute('UPDATE users SET is_vip = 1 WHERE ip = ?', (ip,))
        db.commit()
        return jsonify({'status': 'success', 'message': '制限解除に成功しました'})
    else:
        return jsonify({'status': 'error', 'message': 'パスワードが違います'}), 403

@app.route('/api/increment', methods=['POST'])
def increment_usage():
    """利用回数を増やす（制限チェック）"""
    ip = get_remote_ip()
    status = get_user_status(ip) # ここで日付リセット判定も行われます
    
    current_count = status['count']
    is_vip = status['is_vip']
    
    # --- 判定ロジック ---
    
    # 1. VIP会員なら無条件でOK
    if is_vip:
        # 回数は増やしてもいいし、増やさなくてもいいが、利用OKを返す
        return jsonify({'status': 'ok', 'count': current_count, 'is_vip': True})

    # 2. まだ3回未満なら利用OK（0回, 1回, 2回 の状態）
    if current_count < DAILY_LIMIT:
        new_count = current_count + 1
        db = get_db()
        db.execute('UPDATE users SET count = ? WHERE ip = ?', (new_count, ip))
        db.commit()
        return jsonify({'status': 'ok', 'count': new_count, 'is_vip': False})
    
    # 3. それ以外（3回使い終わっている状態）ならブロック
    else:
        return jsonify({
            'status': 'locked', 
            'message': '本日の無料回数（3回）を終了しました。',
            'count': current_count,
            'is_vip': False
        }), 403

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
