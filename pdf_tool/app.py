import os, uuid, zipfile, io, gc, time, traceback
from flask import Flask, request, render_template, send_file, jsonify
from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image, ImageChops

app = Flask(__name__)
# Renderの一時ディレクトリを使用
UPLOAD_FOLDER = '/tmp'

# --- 設定 ---
DEV_PASS = "admin1234"
USER_PASS = "pro_user_77"
DAILY_LIMIT = 3
usage_tracker = {}

def force_cleanup():
    """メモリをOSに強制的に返却し、SIGKILLを防ぐ"""
    gc.collect()
    time.sleep(0.1)

def make_transparent_efficient(image):
    """
    ピクセルループを使わず、C言語レベルのベクトル演算で透過処理。
    300DPIの大容量画像でもメモリをほぼ消費しません。
    """
    img = image.convert("RGBA")
    r, g, b, a = img.split()
    
    # 245以上の明るさを白と判定（ここを以前のロジックに合わせる）
    mask_r = r.point(lambda x: 255 if x > 245 else 0)
    mask_g = g.point(lambda x: 255 if x > 245 else 0)
    mask_b = b.point(lambda x: 255 if x > 245 else 0)
    
    # RGBすべてが白い部分を特定
    white_mask = ImageChops.multiply(ImageChops.multiply(mask_r, mask_g), mask_b)
    
    # 白い部分のアルファ値を0（透明）にする
    inv_mask = ImageChops.invert(white_mask)
    new_a = ImageChops.multiply(a, inv_mask)
    img.putalpha(new_a)
    
    del r, g, b, a, mask_r, mask_g, mask_b, white_mask, inv_mask, new_a
    return img

def process_pdf_safely(pdf_path, dpi, is_transparent, zip_file, base_name):
    """
    Cairoエンジンを使用し、1ページずつ独立して処理することで
    xref tableエラーとSIGKILLを回避する核心部。
    """
    try:
        info = pdfinfo_from_path(pdf_path)
        total_pages = info["Pages"]
        
        for p in range(1, total_pages + 1):
            # ページごとにPoppler(Cairo)を呼び出すことでメモリをリセット
            pages = convert_from_path(
                pdf_path, 
                dpi=dpi, 
                first_page=p, 
                last_page=p,
                use_pdftocairo=True, # メモリ効率と互換性のためにCairoを強制
                thread_count=1       # 並列化せず1つずつ処理
            )
            
            if not pages: continue
            
            img = pages[0]
            if is_transparent:
                img = make_transparent_efficient(img)
            
            # ZIPに書き込み
            img_io = io.BytesIO()
            img.save(img_io, format='PNG', optimize=False)
            zip_file.writestr(f"{base_name}_{p:03d}.png", img_io.getvalue())
            
            # 1ページごとに完全に破棄
            img_io.close()
            img.close()
            del img, pages
            force_cleanup()
            
        return total_pages
    except Exception as e:
        print(f"ERROR processing PDF: {traceback.format_exc()}")
        return 0

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    force_cleanup()
    pwd = request.form.get('password', '')
    is_pro = (pwd in [DEV_PASS, USER_PASS])
    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0]
    
    files = request.files.getlist('file')
    dpi = int(request.form.get('dpi', 150))
    is_transparent = 'transparent' in request.form
    
    # 無料制限チェック
    if not is_pro:
        now = time.time()
        if ip not in usage_tracker: usage_tracker[ip] = {"count": 0, "reset": now}
        if now - usage_tracker[ip]["reset"] > 86400: usage_tracker[ip] = {"count": 0, "reset": now}
        if usage_tracker[ip]["count"] + len([f for f in files if f.filename != '']) > DAILY_LIMIT:
            return jsonify({"error": "1日の制限枚数を超えました。"}), 403

    zip_buffer = io.BytesIO()
    total_count = 0
    
    try:
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as master_zip:
            for f in files:
                if f.filename == '': continue
                # PDFを一旦ディスクに保存してxref tableエラーを防止
                tmp_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.pdf")
                f.save(tmp_path)
                
                count = process_pdf_safely(tmp_path, dpi, is_transparent, master_zip, os.path.splitext(f.filename)[0])
                total_count += count
                
                if os.path.exists(tmp_path): os.remove(tmp_path)
                force_cleanup()

        if total_count == 0:
            return jsonify({"error": "変換に失敗しました。Popplerの設定を確認してください。"}), 500

        if not is_pro: usage_tracker[ip]["count"] += 1
        
        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name="materials.zip")

    except Exception as e:
        return jsonify({"error": f"予期せぬエラー: {str(e)}"}), 500
