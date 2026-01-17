import os
import sqlite3
from datetime import date
from flask import Flask, render_template, request, jsonify, g

# テンプレートフォルダを明示的に指定
app = Flask(__name__, template_folder='templates')
app.secret_key = os.urandom(24)

# --- 設定 ---
VIP_PASSWORD = os.environ.get("VIP_PASSWORD", "secret_password")
DAILY_LIMIT = 3

# RenderでのDBパス固定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'usage.db')

def get_db():
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
    with app.app_context():
        db = get_db()
        # IPアドレスを主キーにしてユーザーを管理
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                ip TEXT PRIMARY KEY,
                last_date TEXT,
                count INTEGER,
                is_vip INTEGER
            )
        ''')
        db.commit()

init_db()

def get_remote_ip():
    """Render環境下で正しいIPを取得"""
    if request.headers.getlist("X-Forwarded-For"):
        # プロキシ経由の場合、大元のIPを取得
        return request.headers.getlist("X-Forwarded-For")[0]
    return request.remote_addr

def get_user_data_from_db(ip):
    """DBから最新のユーザー情報を取得し、日付変更があればリセットする"""
    today_str = str(date.today())
    db = get_db()
    cursor = db.execute('SELECT * FROM users WHERE ip = ?', (ip,))
    user = cursor.fetchone()
    
    if user is None:
        # 新規ユーザー作成
        db.execute('INSERT INTO users (ip, last_date, count, is_vip) VALUES (?, ?, ?, ?)', 
                   (ip, today_str, 0, 0))
        db.commit()
        return {'date': today_str, 'count': 0, 'is_vip': False}
    
    # 日付チェック
    if user['last_date'] != today_str:
        # 日付が変わっていたらカウントを0にリセット（VIP権限は維持）
        is_vip_status = user['is_vip']
        db.execute('UPDATE users SET last_date = ?, count = 0 WHERE ip = ?', (today_str, ip))
        db.commit()
        return {'date': today_str, 'count': 0, 'is_vip': bool(is_vip_status)}
    
    return {'date': user['last_date'], 'count': user['count'], 'is_vip': bool(user['is_vip'])}

# --- ルーティング ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status', methods=['GET'])
def get_status():
    """現在の状態を返す（画面表示用）"""
    ip = get_remote_ip()
    user = get_user_data_from_db(ip)
    return jsonify(user)

@app.route('/api/unlock', methods=['POST'])
def unlock_limit():
    """パスワード認証（サーバー側でVIPフラグを立てる）"""
    ip = get_remote_ip()
    data = request.get_json() or {}
    input_pass = data.get('password', '')
    
    if input_pass == VIP_PASSWORD:
        db = get_db()
        db.execute('UPDATE users SET is_vip = 1 WHERE ip = ?', (ip,))
        db.commit()
        return jsonify({'status': 'success', 'message': '認証成功'})
    else:
        return jsonify({'status': 'error', 'message': 'パスワードが違います'}), 403

@app.route('/api/increment', methods=['POST'])
def increment_count():
    """【重要】サーバー側でカウント加算と制限チェックを行う"""
    ip = get_remote_ip()
    
    # 最新の状態を取得
    user = get_user_data_from_db(ip)
    
    # VIPなら無条件OK
    if user['is_vip']:
        return jsonify({'status': 'ok', 'count': user['count'], 'is_vip': True})
    
    # 制限チェック（ここがサーバー側の防壁）
    if user['count'] >= DAILY_LIMIT:
        return jsonify({
            'status': 'locked', 
            'message': '本日の利用上限に達しました。',
            'count': user['count'], 
            'is_vip': False
        }), 403
    
    # カウント加算してDB保存
    new_count = user['count'] + 1
    db = get_db()
    db.execute('UPDATE users SET count = ? WHERE ip = ?', (new_count, ip))
    db.commit()
    
    return jsonify({'status': 'ok', 'count': new_count, 'is_vip': False})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
