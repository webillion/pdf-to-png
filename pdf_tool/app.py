import os, uuid, zipfile, io, gc, time, traceback
from flask import Flask, request, render_template, send_file, jsonify
from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image, ImageChops

app = Flask(__name__)
UPLOAD_FOLDER = '/tmp/material_studio'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- 設定 ---
DEV_PASS = "admin1234"
USER_PASS = "pro_user_77"
DAILY_FILE_LIMIT = 3
usage_tracker = {}

def force_cleanup():
    gc.collect()
    time.sleep(0.1)

def make_transparent_robust(image):
    """
    最も安定して白を透過させるロジック。
    各チャンネルを分離して「すべてが245以上」の部分をマスクにします。
    """
    # RGBAに変換
    img = image.convert("RGBA")
    r, g, b, a = img.split()

    # 各色で「245以上（ほぼ白）」の場所を1（白）、それ以外を0（黒）にする
    # 'L'モード（8bit）で処理し、後で論理積をとる
    mask_r = r.point(lambda x: 255 if x > 245 else 0, mode='L')
    mask_g = g.point(lambda x: 255 if x > 245 else 0, mode='L')
    mask_b = b.point(lambda x: 255 if x > 245 else 0, mode='L')

    # R, G, B すべてが白い部分だけを残す（論理積）
    combined_mask = ImageChops.darker(ImageChops.darker(mask_r, mask_g), mask_b)
    
    # 元のアルファチャンネルから、combined_maskが255（白）の場所を0（透明）にする
    # maskを反転（白を黒に、黒を白に）させて元のアルファと掛け合わせる
    inv_mask = ImageChops.invert(combined_mask)
    new_a = ImageChops.darker(a, inv_mask)
    
    img.putalpha(new_a)
    
    # メモリ解放
    del r, g, b, a, mask_r, mask_g, mask_b, combined_mask, inv_mask
    return img

def process_pdf_sequentially(pdf_path, dpi, is_transparent, zip_file, base_name):
    try:
        # PDF情報を取得（ここで落ちる場合はPopplerが未インストール）
        info = pdfinfo_from_path(pdf_path)
        total_pages = info["Pages"]
        processed_count = 0
        
        for p in range(1, min(total_pages, 15) + 1):
            # 1ページずつ読み込み
            pages = convert_from_path(pdf_path, dpi=dpi, first_page=p, last_page=p, thread_count=1)
            if not pages: continue
            
            img = pages[0]
            if is_transparent:
                img = make_transparent_robust(img)
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
        # 詳細なエラーをサーバーログに出力
        print(f"--- 変換エラー詳細 ---")
        traceback.print_exc()
        return 0

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    force_cleanup()
    pwd = request.form.get('password', '')
    is_pro = (pwd == DEV_PASS or pwd == USER_PASS)
    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0]
    
    files = request.files.getlist('file')
    valid_files = [f for f in files if f.filename != '']
    
    if not is_pro:
        # 簡易的な回数制限チェック
        now = time.time()
        if ip not in usage_tracker: usage_tracker[ip] = {"count": 0, "reset": now}
        if now - usage_tracker[ip]["reset"] > 86400: usage_tracker[ip] = {"count": 0, "reset": now}
        if usage_tracker[ip]["count"] + len(valid_files) > DAILY_FILE_LIMIT:
            return jsonify({"error": "無料枠制限（1日3ファイル）を超えました。"}), 403

    try:
        dpi = int(request.form.get('dpi', 150))
        is_transparent = 'transparent' in request.form
        zip_buffer = io.BytesIO()
        total_images = 0
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as master_zip:
            for f in valid_files:
                tmp_name = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.pdf")
                f.save(tmp_name)
                count = convert_pdf_sequentially(tmp_name, dpi, is_transparent, master_zip, os.path.splitext(f.filename)[0])
                total_images += count
                if os.path.exists(tmp_name): os.remove(tmp_name)

        if total_images == 0:
            return jsonify({"error": "変換に失敗しました。PDFの解析ができません（Popplerエラーの可能性）。"}), 500

        if not is_pro: usage_tracker[ip]["count"] += len(valid_files)
        
        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name="materials.zip")

    except Exception as e:
        return jsonify({"error": f"サーバーエラー: {str(e)}"}), 500
    finally:
        force_cleanup()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
