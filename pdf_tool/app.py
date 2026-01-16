import os
from datetime import date
from flask import Flask, render_template, request, jsonify

# テンプレートフォルダの場所を明示的に指定してエラーを防ぐ
app = Flask(__name__, template_folder='templates')
app.secret_key = os.urandom(24)

# --- 設定 ---
VIP_PASSWORD = os.environ.get("VIP_PASSWORD", "secret_password") # 環境変数推奨
DAILY_LIMIT = 3

# ユーザーデータ管理 { 'IPアドレス': {'date': 'yyyy-mm-dd', 'count': 0, 'is_vip': False} }
user_db = {}

def get_remote_ip():
    """Renderなどのプロキシ環境下で正しいIPアドレスを取得"""
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0]
    return request.remote_addr

def get_user_data(ip):
    """ユーザーの利用状況を取得・初期化"""
    today_str = str(date.today())
    
    if ip not in user_db:
        user_db[ip] = {'date': today_str, 'count': 0, 'is_vip': False}
    else:
        # 日付が変わっていたらカウントリセット（VIPフラグは維持するか選択可。今回は維持）
        if user_db[ip]['date'] != today_str:
            user_db[ip]['date'] = today_str
            user_db[ip]['count'] = 0
            
    return user_db[ip]

def make_ui_response(user_data):
    """フロントエンドに返す表示データを作成"""
    current = user_data['count']
    is_vip = user_data['is_vip']
    remaining = max(0, DAILY_LIMIT - current)
    
    # VIPなら無制限表示
    if is_vip:
        return {
            'text_count': "∞ (無制限)",
            'text_status': "制限解除済み：無制限に使用可能です",
            'badge_class': "badge-vip",
            'is_locked': False,
            'is_vip': True
        }
    
    # 通常ユーザー
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
    user = get_user_data(ip)
    
    data = request.get_json() or {}
    input_pass = data.get('password', '')
    
    if input_pass == VIP_PASSWORD:
        user['is_vip'] = True  # VIPフラグを立てる
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
    
    # VIPならカウントに関係なくOK
    if user['is_vip']:
        return jsonify({'status': 'ok', 'ui_data': make_ui_response(user)})
    
    # 制限チェック
    if user['count'] >= DAILY_LIMIT:
        return jsonify({
            'status': 'locked', 
            'message': '利用上限に達しています。',
            'ui_data': make_ui_response(user)
        }), 403
        
    user['count'] += 1
    return jsonify({'status': 'ok', 'ui_data': make_ui_response(user)})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
