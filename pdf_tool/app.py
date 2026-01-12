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
DEVELOPER_PASSWORD = "dev_admin_key"  # あなた（開発者）用
USER_PRO_PASSWORD = "user_pro_key"    # 販売するパスワード
FILE_DAILY_LIMIT = 3
usage_tracker = {} # {IP: {"file_count": 0, "last_reset": timestamp}}
# ==========================================

def get_client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0]

def check_usage_limit(ip):
    now = time.time()
    if ip not in usage_tracker:
        usage_tracker[ip] = {"file_count": 0, "last_reset": now}
    if now - usage_tracker[ip]["last_reset"] > 86400:
        usage_tracker[ip] = {"file_count": 0, "last_reset": now}
    return usage_tracker[ip]["file_count"]

def make_transparent_fast(image):
    """省メモリかつ確実な透過処理"""
    img = image.convert("RGBA")
    r, g, b, a = img.split()
    # 245以上の明るさを白と判定（少し余裕を持たせる）
    mask = Image.eval(lambda r_v, g_v, b_v: 255 if r_v > 245 and g_v > 245 and b_v > 245 else 0, r, g, b)
    # マスクを反転させてアルファチャンネルに適用
    new_a = Image.eval(lambda a_v, m_v: 0 if m_v == 255 else a_v, a, mask)
    img.putalpha(new_a)
    return img

def process_pdf_to_zip(pdf_path, dpi, is_transparent, zip_file, base_filename):
    """1枚ずつ処理して即座に書き込む"""
    success_count = 0
    try:
        # thread_count=1でメモリ爆発を防ぐ
        pages = convert_from_path(pdf_path, dpi=dpi, thread_count=1)
        if not pages:
            return 0
        
        for i, page in enumerate(pages[:15]): # 最大15ページ
            if is_transparent:
                page = make_transparent_fast(page)
            else:
                page = page.convert("RGB")
            
            img_io = io.BytesIO()
            page.save(img_io, format='PNG', optimize=False)
            
            # ZIPに書き込み
            zip_file.writestr(f"{base_filename}_{i+1:03d}.png", img_io.getvalue())
            
            # メモリを徹底的に解放
            img_io.close()
            page.close()
            del page
            success_count += 1
            
        del pages
        gc.collect()
        return success_count
    except Exception as e:
        print(f"Error in {base_filename}: {e}")
        return 0

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    user_ip = get_client_ip()
    user_password = request.form.get('password', '')
    
    # いずれかのパスワードに一致すればPro（無制限）
    is_pro = (user_password == DEVELOPER_PASSWORD) or (user_password == USER_PRO_PASSWORD)

    files = request.files.getlist('file')
    valid_files = [f for f in files if f.filename != '']
    upload_count = len(valid_files)

    if not is_pro:
        current_files = check_usage_limit(user_ip)
        if current_files + upload_count > FILE_DAILY_LIMIT:
            return jsonify({
                "error": f"無料枠は1日{FILE_DAILY_LIMIT}ファイルまでです。パスワードを入力してください。",
                "limit_reached": True
            }), 403

    try:
        dpi = int(request.form.get('dpi', 150))
        is_transparent = 'transparent' in request.form
        
        total_processed_images = 0
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as master_zip:
            for file in valid_files:
                tmp_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.pdf")
                file.save(tmp_path)
                
                # 処理を行い、成功した画像数をカウント
                res = process_pdf_to_zip(tmp_path, dpi, is_transparent, master_zip, os.path.splitext(file.filename)[0])
                total_processed_images += res
                
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

        # 1枚も処理できていなければエラーを返す
        if total_processed_images == 0:
            return jsonify({"error": "PDFから画像を生成できませんでした。ファイルが壊れているか、重すぎます。"}), 500

        if not is_pro:
            usage_tracker[user_ip]["file_count"] += upload_count
        
        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name="materials.zip")

    except Exception as e:
        return jsonify({"error": f"システムエラー: {str(e)}"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
