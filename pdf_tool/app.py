import os
from datetime import date
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
app.secret_key = os.urandom(24)

# 環境変数から取得するか、デフォルト値を設定
VIP_PASSWORD = os.environ.get("VIP_PASSWORD", "secret_password") [cite: 61]
DAILY_LIMIT = 3 [cite: 61]
user_usage_db = {} [cite: 61]

def get_remote_ip():
    """Renderのプロキシ経由で正しいIPを取得 [cite: 61]"""
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0]
    return request.remote_addr

def get_usage_info(ip):
    """日付が変わればカウントをリセット [cite: 61]"""
    today_str = str(date.today())
    if ip not in user_usage_db or user_usage_db[ip]['date'] != today_str:
        user_usage_db[ip] = {'date': today_str, 'count': 0}
    return user_usage_db[ip]

def get_ui_text_data(current_count):
    """UIに表示する文言と状態を生成 [cite: 62]"""
    remaining = max(0, DAILY_LIMIT - current_count)
    is_limit_reached = (remaining <= 0)
    
    display_count = f"{current_count} / {DAILY_LIMIT}" [cite: 62]
    
    if is_limit_reached:
        display_msg = "上限に達しました (パスワード必須)" [cite: 62]
        badge_style = "badge-error" [cite: 62]
        show_pass = True [cite: 62]
    else:
        display_msg = f"あと {remaining} 回 無料です" [cite: 62]
        badge_style = "badge-success" [cite: 62]
        show_pass = False [cite: 62]

    return {
        'text_count': display_count, [cite: 63]
        'text_message': display_msg, [cite: 63]
        'css_badge': badge_style, [cite: 63]
        'show_pass': show_pass [cite: 63]
    }

@app.route('/')
def index():
    return render_template('index.html') [cite: 63]

@app.route('/api/status', methods=['GET'])
def get_status():
    ip = get_remote_ip() [cite: 63]
    usage = get_usage_info(ip) [cite: 63]
    return jsonify(get_ui_text_data(usage['count'])) [cite: 63]

@app.route('/api/check_auth', methods=['POST'])
def check_auth():
    ip = get_remote_ip() [cite: 64]
    usage = get_usage_info(ip) [cite: 64]
    current_count = usage['count']
    
    data = request.get_json() or {}
    input_password = data.get('password', '') [cite: 64]

    authorized = False
    if current_count < DAILY_LIMIT: [cite: 64]
        authorized = True
    elif input_password == VIP_PASSWORD: [cite: 64]
        authorized = True
    
    if authorized:
        usage['count'] += 1 [cite: 64]
        new_ui_data = get_ui_text_data(usage['count']) [cite: 65]
        return jsonify({'status': 'ok', 'ui_data': new_ui_data}) [cite: 65]
    else:
        return jsonify({'status': 'error', 'message': 'パスワードが違います'}), 403 [cite: 65]

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
