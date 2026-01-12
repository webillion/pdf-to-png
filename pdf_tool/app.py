import os, uuid, zipfile, io, gc, time, traceback
from flask import Flask, request, render_template, send_file, jsonify
from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image

app = Flask(__name__)
# Renderでの動作を安定させるための一時フォルダ
UPLOAD_FOLDER = '/tmp/material_studio'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==========================================
# 設定：パスワードと制限
# ==========================================
DEV_PASS = "admin1234"      # 開発者用
USER_PASS = "pro_user_77"   # 一般ユーザー用
DAILY_LIMIT = 3
usage_tracker = {}

def force_cleanup():
    """メモリを強制的に解放しOSに返却しやすくする"""
    gc.collect()
    time.sleep(0.1)

def make_transparent(image):
    """
    以前成功していた透過ロジックの安定版。
    245以上の白を透明に置き換えます。
    """
    img = image.convert("RGBA")
    datas = img.getdata()
    
    new_data = []
    for item in datas:
        # R, G, B すべてが245以上（ほぼ白）ならアルファを0にする
        if item[0] > 245 and item[1] > 245 and item[2] > 245:
            new_data.append((255, 255, 255, 0))
        else:
            new_data.append(item)
    
    img.putdata(new_data)
    return img

def convert_pdf_sequentially(pdf_path, dpi, is_transparent, zip_file, base_name):
    """
    PDFを1ページずつ読み込んで処理。
    これにより1000KB超のファイルでもメモリ爆発を防ぎます。
    """
    try:
        info = pdfinfo_from_path(pdf_path)
        total_pages = info["Pages"]
        processed_count = 0
        
        # 安全のため15ページ上限（必要に応じて変更可）
        for p in range(1, min(total_pages, 15) + 1):
            # 特定の1ページだけをメモリに呼ぶ
            pages = convert_from_path(pdf_path, dpi=dpi, first_page=p, last_page=p, thread_count=1)
            if not pages: continue
            
            img = pages[0]
            if is_transparent:
                img = make_transparent(img)
            else:
                img = img.convert("RGB")
            
            img_io = io.BytesIO()
            img.save(img_io, format='PNG', optimize=False)
            
            # ZIPに書き込み
            zip_file.writestr(f"{base_name}_{p:03d}.png", img_io.getvalue())
            
            # 1ページごとにメモリを徹底破棄
            img_io.close()
            img.close()
            del img, pages
            force_cleanup()
            processed_count += 1
            
        return processed_count
    except Exception as e:
        print(f"DEBUG Error: {traceback.format_exc()}")
        return 0

@app.route('/')
def index():
    force_cleanup()
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    force_cleanup()
    
    pwd = request.form.get('password', '')
    is_pro = (pwd == DEV_PASS or pwd == USER_PASS)
    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0]
    
    files = request.files.getlist('file')
    valid_files = [f for f in files if f.filename != '']
    
    # パスワードがない場合のみ制限をかける
    if not is_pro:
        now = time.time()
        if ip not in usage_tracker: usage_tracker[ip] = {"count": 0, "reset": now}
        if now - usage_tracker[ip]["reset"] > 86400: usage_tracker[ip] = {"count": 0, "reset": now}
        if usage_tracker[ip]["count"] + len(valid_files) > DAILY_LIMIT:
            return jsonify({"error": "無料枠制限(1日3枚)を超えました。"}), 403

    try:
        dpi = int(request.form.get('dpi', 150))
        is_transparent = 'transparent' in request.form
        zip_buffer = io.BytesIO()
        total_images = 0
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as master_zip:
            for f in valid_files:
                tmp_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.pdf")
                f.save(tmp_path)
                
                # 逐次変換の呼び出し
                count = convert_pdf_sequentially(tmp_path, dpi, is_transparent, master_zip, os.path.splitext(f.filename)[0])
                total_images += count
                
                if os.path.exists(tmp_path): os.remove(tmp_path)
                force_cleanup()

        if total_images == 0:
            return jsonify({"error": "変換に失敗しました。PDFを解析できません。"}), 500

        if not is_pro:
            usage_tracker[ip]["count"] += len(valid_files)
        
        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name="materials.zip")

    except Exception as e:
        return jsonify({"error": f"サーバーエラー: {str(e)}"}), 500
    finally:
        force_cleanup()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
