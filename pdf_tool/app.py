import os, uuid, zipfile, io, gc, time, traceback
from flask import Flask, request, render_template, send_file, jsonify
from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image, ImageChops

app = Flask(__name__)
UPLOAD_FOLDER = '/tmp/material_studio'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==========================================
# 設定
# ==========================================
DEV_PASS = "admin1234"      # 開発者用
USER_PASS = "pro_user_77"   # 一般Pro用
DAILY_LIMIT = 3
usage_tracker = {}

def force_cleanup():
    """メモリを強制解放"""
    gc.collect()
    time.sleep(0.1)

def make_transparent_memory_safe(image):
    """
    【修正の要】
    getdata()（ループ処理）を廃止し、ImageChops（画像演算）を使用。
    これにより、300DPIでもメモリを消費せず、一瞬で背景を抜けます。
    """
    # 作業用にRGBA変換
    img = image.convert("RGBA")
    r, g, b, a = img.split()
    
    # 1. 閾値判定（245以上の明るさを白とみなす）
    # point関数はC言語レベルで高速動作し、メモリを食いません
    fn = lambda x: 255 if x > 245 else 0
    mask_r = r.point(fn, mode='L')
    mask_g = g.point(fn, mode='L')
    mask_b = b.point(fn, mode='L')
    
    # 2. マスク合成（RもGもBも「白」である場所を特定）
    # multiplyは「AND演算」と同じ働きをします
    white_mask = ImageChops.multiply(mask_r, mask_g)
    white_mask = ImageChops.multiply(white_mask, mask_b)
    
    # 3. 透過適用
    # 「白マスク」の部分を「透明」にしたいので、マスクを反転させます
    # 白(255) -> 透明(0) にするため、反転したマスクをアルファチャンネルに掛け合わせます
    alpha_mask = ImageChops.invert(white_mask)
    new_a = ImageChops.multiply(a, alpha_mask)
    
    img.putalpha(new_a)
    
    # メモリ掃除
    del r, g, b, a, mask_r, mask_g, mask_b, white_mask, alpha_mask
    return img

def convert_pdf_sequentially(pdf_path, dpi, is_transparent, zip_file, base_name):
    """1ページずつメモリに展開して処理・保存・廃棄"""
    try:
        info = pdfinfo_from_path(pdf_path)
        total_pages = info["Pages"]
        processed_count = 0
        
        for p in range(1, min(total_pages, 15) + 1):
            # 1ページだけ読み込み
            pages = convert_from_path(pdf_path, dpi=dpi, first_page=p, last_page=p, thread_count=1)
            if not pages: continue
            
            img = pages[0]
            if is_transparent:
                # 高速・軽量版の透過処理を使用
                img = make_transparent_memory_safe(img)
            else:
                img = img.convert("RGB")
            
            img_io = io.BytesIO()
            # 圧縮レベルを下げる(optimize=False)ことでCPU負荷も軽減
            img.save(img_io, format='PNG', optimize=False)
            
            # ZIPへ書き込み
            zip_file.writestr(f"{base_name}_{p:03d}.png", img_io.getvalue())
            
            # 即座にメモリ破棄
            img_io.close()
            img.close()
            del img, pages
            force_cleanup()
            processed_count += 1
            
        return processed_count
    except Exception as e:
        print(f"Internal Error: {traceback.format_exc()}")
        return 0

# ==========================================
# ルーティング
# ==========================================

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
    
    if not is_pro:
        now = time.time()
        if ip not in usage_tracker: usage_tracker[ip] = {"count": 0, "reset": now}
        if now - usage_tracker[ip]["reset"] > 86400: usage_tracker[ip] = {"count": 0, "reset": now}
        if usage_tracker[ip]["count"] + len(valid_files) > DAILY_LIMIT:
            return jsonify({"error": "無料枠（1日3ファイル）を超えました。パスワードを入力してください。"}), 403

    try:
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
            return jsonify({"error": "変換に失敗しました。PDFの読み込みエラーか、メモリ不足です。"}), 500

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
