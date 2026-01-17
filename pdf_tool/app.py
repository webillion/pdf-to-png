import os
import sqlite3
from datetime import date
from flask import Flask, render_template, request, jsonify, g

# テンプレートフォルダを明示的に指定
app = Flask(__name__, template_folder='templates')
app.secret_key = os.urandom(24)

# --- 設定 ---
# 環境変数 VIP_PASSWORD がなければ "secret_password" になります
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
        # テーブル作成（存在しない場合のみ）
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                ip TEXT PRIMARY KEY,
                last_date TEXT,
                count INTEGER,
                is_vip INTEGER
            )
        ''')
        db.commit()

# アプリ起動時にDB初期化
init_db()

def get_remote_ip():
    """Render環境下で正しいIPを取得"""
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0]
    return request.remote_addr

def get_user_data(ip):
    """ユーザーデータを取得・日付更新があればリセット"""
    today_str = str(date.today())
    db = get_db()
    cursor = db.execute('SELECT * FROM users WHERE ip = ?', (ip,))
    user = cursor.fetchone()
    
    if user is None:
        # 新規
        db.execute('INSERT INTO users (ip, last_date, count, is_vip) VALUES (?, ?, ?, ?)', 
                   (ip, today_str, 0, 0))
        db.commit()
        return {'date': today_str, 'count': 0, 'is_vip': False}
    
    # 日付が変わっているかチェック
    if user['last_date'] != today_str:
        # 日付更新＆カウントリセット（VIPは維持）
        is_vip = user['is_vip']
        db.execute('UPDATE users SET last_date = ?, count = 0 WHERE ip = ?', (today_str, ip))
        db.commit()
        return {'date': today_str, 'count': 0, 'is_vip': bool(is_vip)}
    
    return {'date': user['last_date'], 'count': user['count'], 'is_vip': bool(user['is_vip'])}

# --- ルーティング ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status', methods=['GET'])
def get_status():
    """現在の状態を返す"""
    ip = get_remote_ip()
    user = get_user_data(ip)
    return jsonify(user)

@app.route('/api/unlock', methods=['POST'])
def unlock_limit():
    """パスワード認証"""
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
    """カウント加算"""
    ip = get_remote_ip()
    user = get_user_data(ip)
    
    # VIPならカウント無視でOK
    if user['is_vip']:
        return jsonify({'status': 'ok', 'count': user['count'], 'is_vip': True})
    
    # 制限チェック
    if user['count'] >= DAILY_LIMIT:
        return jsonify({'status': 'locked', 'count': user['count'], 'is_vip': False}), 403
    
    # 加算
    new_count = user['count'] + 1
    db = get_db()
    db.execute('UPDATE users SET count = ? WHERE ip = ?', (new_count, ip))
    db.commit()
    
    return jsonify({'status': 'ok', 'count': new_count, 'is_vip': False})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
