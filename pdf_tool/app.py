import os
from datetime import date
from flask import Flask, render_template, request, jsonify

# Flaskのテンプレートフォルダを明示的に指定
app = Flask(__name__, template_folder='templates')
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

def get_ui_text_data(current_count, unlocked=False):
    remaining = max(0, DAILY_LIMIT - current_count)
    is_limit_reached = (remaining <= 0) and not unlocked
    display_count = f"{current_count} / {DAILY_LIMIT}"
    
    if unlocked:
        display_msg = "制限解除済み：無制限で使えます"
        badge_style = "badge-success"
        show_pass = False
    elif is_limit_reached:
        display_msg = "上限に達しました (パスワード必須)"
        badge_style = "badge-error"
        show_pass = True
    else:
        display_msg = f"あと {remaining} 回 無料です"
        badge_style = "badge-success"
        show_pass = False

    return {
        'text_count': display_count, 'text_message': display_msg,
        'css_badge': badge_style, 'show_pass': show_pass
    }

@app.route('/')
def index():
    # フォルダがない、またはファイルがないとここでStatus 1が出る
    return render_template('index.html')

@app.route('/api/status', methods=['GET'])
def get_status():
    ip = get_remote_ip()
    usage = get_usage_info(ip)
    return jsonify(get_ui_text_data(usage['count']))

@app.route('/api/check_auth', methods=['POST'])
def check_auth():
    ip = get_remote_ip()
    usage = get_usage_info(ip)
    data = request.get_json() or {}
    input_password = data.get('password', '')
    is_correct_pass = (input_password == VIP_PASSWORD)
    authorized = (usage['count'] < DAILY_LIMIT) or is_correct_pass
    
    if authorized:
        if not is_correct_pass: usage['count'] += 1
        return jsonify({
            'status': 'ok', 
            'ui_data': get_ui_text_data(usage['count'], unlocked=is_correct_pass),
            'message': "制限を解除しました。無制限で使えます。" if is_correct_pass else ""
        })
    return jsonify({'status': 'error', 'message': 'パスワードが違います'}), 403

if __name__ == '__main__':
    # RenderはPORT環境変数を要求するため、この書き方が必須
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
