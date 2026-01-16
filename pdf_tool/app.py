import os
from datetime import date
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
app.secret_key = os.urandom(24)

VIP_PASSWORD = "secret_password"
DAILY_LIMIT = 3
user_usage_db = {}

def get_remote_ip():
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0]
    return request.remote_addr

def get_usage_info(ip):
    today_str = str(date.today())
    if ip not in user_usage_db or user_usage_db[ip]['date'] != today_str:
        user_usage_db[ip] = {'date': today_str, 'count': 0}
    return user_usage_db[ip]

# --- UI表示用の文言・デザインをPythonで作る関数 ---
def get_ui_text_data(current_count):
    remaining = max(0, DAILY_LIMIT - current_count)
    is_limit_reached = (remaining <= 0)

    # 画面に表示するテキストをここで作成
    display_count = f"{current_count} / {DAILY_LIMIT}"
    
    if is_limit_reached:
        display_msg = "上限に達しました (パスワード必須)"
        badge_style = "badge-error"
        show_pass = True
    else:
        display_msg = f"あと {remaining} 回 無料です"
        badge_style = "badge-success"
        show_pass = False

    return {
        'text_count': display_count,
        'text_message': display_msg,
        'css_badge': badge_style,
        'show_pass': show_pass
    }

# --- ルーティング ---

@app.route('/')
def index():
    # 変数を埋め込まず、ただHTMLファイルを返すだけにする
    # これによりHTML側に {{ }} を書く必要がなくなります
    return render_template('index.html')

@app.route('/api/status', methods=['GET'])
def get_status():
    """ページを開いた直後に呼ばれる、初期状態取得用API"""
    ip = get_remote_ip()
    usage = get_usage_info(ip)
    # 現在の状況を計算してJSONで返す
    ui_data = get_ui_text_data(usage['count'])
    return jsonify(ui_data)

@app.route('/api/check_auth', methods=['POST'])
def check_auth():
    """変換実行時の認証用API"""
    ip = get_remote_ip()
    usage = get_usage_info(ip)
    current_count = usage['count']
    
    data = request.get_json() or {}
    input_password = data.get('password', '')

    authorized = False
    
    if current_count < DAILY_LIMIT:
        authorized = True
    elif input_password == VIP_PASSWORD:
        authorized = True
    
    if authorized:
        usage['count'] += 1
        # 更新後のUIデータを作成
        new_ui_data = get_ui_text_data(usage['count'])
        return jsonify({'status': 'ok', 'ui_data': new_ui_data})
    else:
        return jsonify({'status': 'error', 'message': 'パスワードが違います'}), 403

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
