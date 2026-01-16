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
DATABASE = 'usage.db'

# --- データベース接続ヘルパー ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        # 辞書形式でデータを扱えるようにする
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    """テーブルが存在しない場合に作成する"""
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                ip TEXT PRIMARY KEY,
                last_date TEXT,
                count INTEGER,
                is_vip INTEGER
            )
        ''')
        db.commit()

# アプリ起動時にDB初期化を実行（初回のみ）
init_db()

# --- ロジック ---

def get_remote_ip():
    """Renderなどのプロキシ環境下で正しいIPアドレスを取得"""
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0]
    return request.remote_addr

def get_user_data(ip):
    """ユーザーの利用状況をDBから取得・更新"""
    today_str = str(date.today())
    db = get_db()
    cursor = db.cursor()
    
    # ユーザー検索
    cursor.execute('SELECT * FROM users WHERE ip = ?', (ip,))
    user = cursor.fetchone()
    
    if user is None:
        # 新規ユーザー
        cursor.execute(
            'INSERT INTO users (ip, last_date, count, is_vip) VALUES (?, ?, ?, ?)',
            (ip, today_str, 0, 0)
        )
        db.commit()
        return {'date': today_str, 'count': 0, 'is_vip': False}
    else:
        # 既存ユーザー：日付チェック
        user_date = user['last_date']
        user_count = user['count']
        is_vip = bool(user['is_vip'])
        
        if user_date != today_str:
            # 日付が変わっているのでカウントリセット（VIPは維持）
            cursor.execute(
                'UPDATE users SET last_date = ?, count = 0 WHERE ip = ?',
                (today_str, ip)
            )
            db.commit()
            return {'date': today_str, 'count': 0, 'is_vip': is_vip}
        else:
            # 当日データそのまま
            return {'date': user_date, 'count': user_count, 'is_vip': is_vip}

def make_ui_response(user_data):
    """フロントエンドに返す表示データを作成"""
    current = user_data['count']
    is_vip = user_data['is_vip']
    remaining = max(0, DAILY_LIMIT - current)
    
    if is_vip:
        return {
            'text_count': "∞ (無制限)",
            'text_status': "制限解除済み：無制限に使用可能です",
            'badge_class': "badge-vip",
            'is_locked': False,
            'is_vip': True
        }
    
    if remaining <= 0:
        return {
            'text_count': f"{current} / {DAILY_LIMIT}",
            'text_status': "本日の上限に達しました。パスワードで解除してください。",
            'badge_class': "badge-error",
            'is_locked': True,
            'is_vip': False
        }
    else:
        return {
            'text_count': f"{current} / {DAILY_LIMIT}",
            'text_status': f"あと {remaining} 回 利用可能です",
            'badge_class': "badge-success",
            'is_locked': False,
            'is_vip': False
        }

# --- ルーティング ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status', methods=['GET'])
def get_status():
    """現在のステータスを返す"""
    ip = get_remote_ip()
    user = get_user_data(ip)
    return jsonify(make_ui_response(user))

@app.route('/api/unlock', methods=['POST'])
def unlock_limit():
    """パスワード認証と制限解除"""
    ip = get_remote_ip()
    data = request.get_json() or {}
    input_pass = data.get('password', '')
    
    if input_pass == VIP_PASSWORD:
        db = get_db()
        db.execute('UPDATE users SET is_vip = 1 WHERE ip = ?', (ip,))
        db.commit()
        
        # 更新後のデータを取得
        user = get_user_data(ip)
        return jsonify({
            'status': 'success',
            'message': '認証成功：制限が解除されました。',
            'ui_data': make_ui_response(user)
        })
    else:
        return jsonify({'status': 'error', 'message': 'パスワードが違います'}), 403

@app.route('/api/increment', methods=['POST'])
def increment_count():
    """変換実行時にカウントを増やす"""
    ip = get_remote_ip()
    user = get_user_data(ip)
    
    if user['is_vip']:
        return jsonify({'status': 'ok', 'ui_data': make_ui_response(user)})
    
    if user['count'] >= DAILY_LIMIT:
        return jsonify({
            'status': 'locked', 
            'message': '利用上限に達しています。',
            'ui_data': make_ui_response(user)
        }), 403
        
    # カウントアップ
    db = get_db()
    db.execute('UPDATE users SET count = count + 1 WHERE ip = ?', (ip,))
    db.commit()
    
    # 再取得して返す
    updated_user = get_user_data(ip)
    return jsonify({'status': 'ok', 'ui_data': make_ui_response(updated_user)})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
