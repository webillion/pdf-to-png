import os, uuid, zipfile, io, gc, time
from flask import Flask, request, render_template, send_file, jsonify
from pdf2image import convert_from_path
from PIL import Image

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
UPLOAD_FOLDER = 'temp_storage'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==========================================
# 設定エリア
# ==========================================
PRO_PASSWORD = "your_secret_password"  # あなただけが知るパスワード
FILE_DAILY_LIMIT = 3                   # 1日の最大「ファイル数」
usage_tracker = {}                     # {IP: {"file_count": 0, "last_reset": timestamp}}
# ==========================================

def get_client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0]

def check_usage_limit(ip):
    now = time.time()
    if ip not in usage_tracker:
        usage_tracker[ip] = {"file_count": 0, "last_reset": now}
    
    # 24時間経過でリセット
    if now - usage_tracker[ip]["last_reset"] > 86400:
        usage_tracker[ip] = {"file_count": 0, "last_reset": now}
    
    return usage_tracker[ip]["file_count"]

def make_transparent(image):
    """白背景をより確実に透過させるロジック"""
    img = image.convert("RGBA")
    datas = img.getdata()
    
    new_data = []
    for item in datas:
        # 真っ白に近い(R,G,B > 250)ピクセルを完全に透明にする
        if item[0] > 250 and item[1] > 250 and item[2] > 250:
            new_data.append((255, 255, 255, 0))
        else:
            new_data.append(item)
    
    img.putdata(new_data)
    return img

def process_pdf_to_zip(pdf_path, dpi, is_transparent, zip_file, base_filename):
    try:
        pages = convert_from_path(pdf_path, dpi=dpi, thread_count=1)
        for i, page in enumerate(pages[:15]):
            if is_transparent:
                page = make_transparent(page)
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
    user_ip = get_client_ip()
    user_password = request.form.get('password', '')
    is_pro = (user_password == PRO_PASSWORD)

    files = request.files.getlist('file')
    upload_count = len([f for f in files if f.filename != ''])

    # 無料ユーザーの制限チェック
    if not is_pro:
        current_files = check_usage_limit(user_ip)
        if current_files + upload_count > FILE_DAILY_LIMIT:
            return jsonify({
                "error": f"1日の制限数を超えています（残り: {FILE_DAILY_LIMIT - current_files}ファイル）。",
                "limit_reached": True
            }), 403

    try:
        dpi = int(request.form.get('dpi', 150))
        is_transparent = 'transparent' in request.form
        
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as master_zip:
            processed_count = 0
            for file in files:
                if file.filename.lower().endswith('.pdf'):
                    processed_count += 1
                    tmp_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.pdf")
                    file.save(tmp_path)
                    process_pdf_to_zip(tmp_path, dpi, is_transparent, master_zip, os.path.splitext(file.filename)[0])
                    if os.path.exists(tmp_path): os.remove(tmp_path)

        if not is_pro:
            usage_tracker[user_ip]["file_count"] += processed_count
        
        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name="output.zip")

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
