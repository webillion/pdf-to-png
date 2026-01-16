import os
from datetime import date
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
app.secret_key = os.urandom(24)

# 制限設定
VIP_PASSWORD = "secret_password"  # 必要に応じて変更
DAILY_LIMIT = 3
user_usage_db = {} [cite: 61]

def get_remote_ip():
    """Renderのプロキシ環境で正しいIPを取得"""
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0]
    return request.remote_addr [cite: 61, 64]

def get_usage_info(ip):
    """日付ごとの利用回数を管理"""
    today_str = str(date.today())
    if ip not in user_usage_db or user_usage_db[ip]['date'] != today_str:
        user_usage_db[ip] = {'date': today_str, 'count': 0}
    return user_usage_db[ip] [cite: 61]

def get_ui_text_data(current_count, unlocked=False):
    """UI表示用の文言を生成"""
    remaining = max(0, DAILY_LIMIT - current_count)
    is_limit_reached = (remaining <= 0) and not unlocked [cite: 62]

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
        show_pass = False [cite: 62]

    return {
        'text_count': display_count,
        'text_message': display_msg,
        'css_badge': badge_style,
        'show_pass': show_pass
    } [cite: 63]

@app.route('/')
def index():
    """templates/index.htmlを呼び出す"""
    return render_template('index.html') [cite: 63]

@app.route('/api/status', methods=['GET'])
def get_status():
    """初期状態の取得"""
    ip = get_remote_ip()
    usage = get_usage_info(ip)
    ui_data = get_ui_text_data(usage['count'])
    return jsonify(ui_data) [cite: 63]

@app.route('/api/check_auth', methods=['POST'])
def check_auth():
    """パスワード認証と制限解除ボタンの処理"""
    ip = get_remote_ip()
    usage = get_usage_info(ip)
    
    data = request.get_json() or {}
    input_password = data.get('password', '')

    # パスワードが一致するか、無料枠内であれば許可
    is_correct_pass = (input_password == VIP_PASSWORD)
    authorized = (usage['count'] < DAILY_LIMIT) or is_correct_pass [cite: 64]
    
    if authorized:
        # 正しいパスワードが入力された場合はカウントを増やさない、または特別なフラグを立てる等の処理
        if not is_correct_pass:
            usage['count'] += 1 [cite: 65]
        
        ui_data = get_ui_text_data(usage['count'], unlocked=is_correct_pass)
        return jsonify({
            'status': 'ok', 
            'ui_data': ui_data,
            'message': "制限を解除しました。無制限で使えます。" if is_correct_pass else ""
        }) [cite: 65]
    else:
        return jsonify({'status': 'error', 'message': '上限に達しています。パスワードを入力してください。'}), 403 [cite: 65]

if __name__ == '__main__':
    # Renderのポート指定に対応
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
