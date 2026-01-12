import os, uuid, zipfile, io, gc, time, traceback
from flask import Flask, request, render_template, send_file, jsonify
from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image

app = Flask(__name__)
# Renderでの一時保存先
UPLOAD_FOLDER = '/tmp/material_studio'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DEV_PASS = "admin1234"
USER_PASS = "pro_user_77"
DAILY_LIMIT = 3
usage_tracker = {}

def force_cleanup():
    gc.collect()
    time.sleep(0.1)

def make_transparent(image):
    """以前成功していた高精度な透過ロジック"""
    img = image.convert("RGBA")
    datas = img.getdata()
    new_data = []
    for item in datas:
        # 白（245以上）を透明に
        if item[0] > 245 and item[1] > 245 and item[2] > 245:
            new_data.append((255, 255, 255, 0))
        else:
            new_data.append(item)
    img.putdata(new_data)
    return img

def convert_pdf_sequentially(pdf_path, dpi, is_transparent, zip_file, base_name):
    """1ページずつ処理してメモリ負荷を最小化"""
    try:
        info = pdfinfo_from_path(pdf_path)
        total_pages = info["Pages"]
        processed_count = 0
        for p in range(1, min(total_pages, 15) + 1):
            pages = convert_from_path(pdf_path, dpi=dpi, first_page=p, last_page=p, thread_count=1)
            if not pages: continue
            img = pages[0]
            if is_transparent:
                img = make_transparent(img)
            else:
                img = img.convert("RGB")
            img_io = io.BytesIO()
            img.save(img_io, format='PNG', optimize=False)
            zip_file.writestr(f"{base_name}_{p:03d}.png", img_io.getvalue())
            img_io.close()
            img.close()
            del img, pages
            force_cleanup()
            processed_count += 1
        return processed_count
    except Exception as e:
        print(f"Server Internal Error: {traceback.format_exc()}")
        return 0

@app.route('/')
def index():
    force_cleanup()
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    try:
        force_cleanup()
        pwd = request.form.get('password', '')
        is_pro = (pwd == DEV_PASS or pwd == USER_PASS)
        ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0]
        files = request.files.getlist('file')
        valid_files = [f for f in files if f.filename != '']
        
        if not is_pro:
            now = time.time()
            if ip not in usage_tracker: usage_tracker[ip] = {"count": 0, "reset": now}
            if now - usage_tracker[ip]["reset"] > 86400: usage_tracker[ip] = {"count": 0, "reset": now}
            if usage_tracker[ip]["count"] + len(valid_files) > DAILY_LIMIT:
                return jsonify({"error": "1日の制限枚数を超えました。"}), 403

        dpi = int(request.form.get('dpi', 150))
        is_transparent = 'transparent' in request.form
        zip_buffer = io.BytesIO()
        total_images = 0
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as master_zip:
            for f in valid_files:
                tmp_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.pdf")
                f.save(tmp_path)
                count = convert_pdf_sequentially(tmp_path, dpi, is_transparent, master_zip, os.path.splitext(f.filename)[0])
                total_images += count
                if os.path.exists(tmp_path): os.remove(tmp_path)
                force_cleanup()

        if total_images == 0:
            return jsonify({"error": "PDFの解析に失敗しました。Popplerが未インストールの可能性があります。"}), 500

        if not is_pro: usage_tracker[ip]["count"] += len(valid_files)
        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name="materials.zip")

    except Exception as e:
        # 万が一の際も必ずJSONを返す
        return jsonify({"error": f"サーバーエラーが発生しました: {str(e)}"}), 500
    finally:
        force_cleanup()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
