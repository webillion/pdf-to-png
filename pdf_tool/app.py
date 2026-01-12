import os, uuid, zipfile, io, gc, time
from flask import Flask, request, render_template, send_file, jsonify
from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024 # 100MBまで許可
UPLOAD_FOLDER = 'temp_storage'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- 設定 ---
DEV_PASS = "dev_admin_key"
USER_PASS = "user_pro_key"
FILE_LIMIT = 3
usage_tracker = {}

def get_client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0]

def make_transparent_extreme(image):
    """中間データを一切作らない究極の透過処理"""
    img = image.convert("RGBA")
    # 明るい部分を特定してアルファを0にする（高速・低メモリ）
    r, g, b, a = img.split()
    # 245以上の白をマスク
    mask = Image.eval(lambda r_v, g_v, b_v: 255 if r_v > 245 and g_v > 245 and b_v > 245 else 0, r, g, b)
    new_a = Image.eval(lambda a_v, m_v: 0 if m_v == 255 else a_v, a, mask)
    img.putalpha(new_a)
    # 分解したデータを即時削除
    del r, g, b, a, mask
    return img

def process_single_pdf_sequentially(pdf_path, dpi, is_transparent, zip_file, base_filename):
    """PDFを1ページずつ読み込んで処理する（最も負荷が低い方法）"""
    try:
        # PDFの情報を取得
        info = pdfinfo_from_path(pdf_path)
        total_pages = info["Pages"]
        
        success_count = 0
        # 最大15ページまで1ページずつループ
        for i in range(1, min(total_pages, 15) + 1):
            # first_page と last_page を同じにして、1枚だけをメモリに呼ぶ
            page_list = convert_from_path(pdf_path, dpi=dpi, first_page=i, last_page=i, thread_count=1)
            if not page_list: continue
            
            page = page_list[0]
            if is_transparent:
                page = make_transparent_extreme(page)
            else:
                page = page.convert("RGB")
            
            img_io = io.BytesIO()
            page.save(img_io, format='PNG', optimize=False)
            zip_file.writestr(f"{base_filename}_{i:03d}.png", img_io.getvalue())
            
            # 1ページごとに徹底的に掃除
            img_io.close()
            page.close()
            del page, page_list
            gc.collect() 
            success_count += 1
            
        return success_count
    except Exception as e:
        print(f"Error processing {base_filename}: {e}")
        return 0

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    user_ip = get_client_ip()
    pwd = request.form.get('password', '')
    is_pro = (pwd == DEV_PASS or pwd == USER_PASS)
    files = request.files.getlist('file')
    valid_files = [f for f in files if f.filename != '']
    
    if not is_pro:
        now = time.time()
        if user_ip not in usage_tracker: usage_tracker[user_ip] = {"count": 0, "reset": now}
        if now - usage_tracker[user_ip]["reset"] > 86400: usage_tracker[user_ip] = {"count": 0, "reset": now}
        if usage_tracker[user_ip]["count"] + len(valid_files) > FILE_LIMIT:
            return jsonify({"error": "無料枠制限（1日3枚）を超えました。Proパスワードを入力してください。"}), 403

    try:
        dpi = int(request.form.get('dpi', 150))
        is_transparent = 'transparent' in request.form
        zip_buffer = io.BytesIO()
        processed_total = 0
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as master_zip:
            for file in valid_files:
                tmp_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.pdf")
                file.save(tmp_path)
                
                # 逐次処理実行
                res = process_single_pdf_sequentially(tmp_path, dpi, is_transparent, master_zip, os.path.splitext(file.filename)[0])
                processed_total += res
                
                if os.path.exists(tmp_path): os.remove(tmp_path)
                gc.collect()

        if processed_total == 0:
            return jsonify({"error": "画像が生成されませんでした。PDFが空か、処理に失敗しました。"}), 500

        if not is_pro: usage_tracker[user_ip]["count"] += len(valid_files)
        
        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name="materials.zip")

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
