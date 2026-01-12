import os, uuid, zipfile, io, gc, time
from flask import Flask, request, render_template, send_file, jsonify
from pdf2image import convert_from_path

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
UPLOAD_FOLDER = 'temp_storage'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- 設定：ライセンスと制限 ---
PRO_PASSWORD = "your_pro_key_123"  # 販売するパスワード
FREE_LIMIT = 3
usage_tracker = {}

def check_usage_limit(ip):
    current_time = time.time()
    if ip not in usage_tracker:
        usage_tracker[ip] = {"count": 0, "last_reset": current_time}
    if current_time - usage_tracker[ip]["last_reset"] > 86400: # 24時間でリセット
        usage_tracker[ip] = {"count": 0, "last_reset": current_time}
    return usage_tracker[ip]["count"]

def process_pdf_to_zip(pdf_path, dpi, is_transparent, zip_file, base_filename):
    try:
        pages = convert_from_path(pdf_path, dpi=dpi, thread_count=1)
        for i, page in enumerate(pages[:15]):
            if is_transparent:
                page = page.convert("RGBA")
                datas = page.getdata()
                new_data = [(255,255,255,0) if d[0]>240 and d[1]>240 and d[2]>240 else d for d in datas]
                page.putdata(new_data)
            else:
                page = page.convert("RGB")
            
            img_io = io.BytesIO()
            page.save(img_io, format='PNG', optimize=False)
            zip_file.writestr(f"{base_filename}_{i+1:03d}.png", img_io.getvalue())
            img_io.close()
            page.close()
            del page
        del pages
        gc.collect()
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    # ユーザー情報の取得
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0]
    provided_password = request.form.get('password', '')
    
    # ライセンスチェック
    is_pro = (provided_password == PRO_PASSWORD)
    
    # 無料枠チェック（プロでない場合のみ）
    if not is_pro:
        current_count = check_usage_limit(user_ip)
        if current_count >= FREE_LIMIT:
            return jsonify({
                "error": "本日の無料枠（3回）を超えました。パスワードを入力するか明日再度お試しください。",
                "limit_reached": True
            }), 403

    try:
        files = request.files.getlist('file')
        if not files or files[0].filename == '':
            return jsonify({"error": "ファイルが未選択です"}), 400

        selected_dpi = int(request.form.get('dpi', 150))
        is_transparent = 'transparent' in request.form
        
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as master_zip:
            for file in files[:20]:
                if file.filename.lower().endswith('.pdf'):
                    tmp_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.pdf")
                    file.save(tmp_path)
                    process_pdf_to_zip(tmp_path, selected_dpi, is_transparent, master_zip, os.path.splitext(file.filename)[0])
                    if os.path.exists(tmp_path): os.remove(tmp_path)

        # 成功時、無料ユーザーのみカウントアップ
        if not is_pro:
            usage_tracker[user_ip]["count"] += 1
        
        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name="materials.zip")

    except Exception as e:
        return jsonify({"error": f"サーバーエラー: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
