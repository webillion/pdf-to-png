import os, uuid, zipfile, io, gc, time, traceback
from flask import Flask, request, render_template, send_file, jsonify
from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image, ImageChops

app = Flask(__name__)
# Renderの一時フォルダを使用
UPLOAD_FOLDER = '/tmp/material_studio'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==========================================
# 設定：パスワードと制限
# ==========================================
DEV_PASS = "admin1234"      # 開発者用パスワード
USER_PASS = "pro_user_77"   # 一般Proユーザー用パスワード
DAILY_LIMIT = 3             # 1日のファイル数制限
usage_tracker = {}

# ==========================================
# 内部関数
# ==========================================

def force_cleanup():
    """メモリを強制的に解放しOSに返却しやすくする"""
    gc.collect()
    time.sleep(0.1)

def make_transparent_robust(image):
    """
    提示された画像のように、白背景だけを綺麗に抜くロジック。
    画像やグレー背景は保持されます。
    """
    img = image.convert("RGBA")
    r, g, b, a = img.split()
    
    # 245以上の明るさ（ほぼ白）の部分を特定
    # 写真やグレー背景(例えば200くらい)は透過されずに残ります
    mask_r = r.point(lambda x: 255 if x > 245 else 0, mode='L')
    mask_g = g.point(lambda x: 255 if x > 245 else 0, mode='L')
    mask_b = b.point(lambda x: 255 if x > 245 else 0, mode='L')

    # RGBすべてが白い部分の共通領域を作成
    combined_mask = ImageChops.darker(ImageChops.darker(mask_r, mask_g), mask_b)
    
    # 白い部分のアルファチャンネルを0（透明）にする
    inv_mask = ImageChops.invert(combined_mask)
    new_a = ImageChops.darker(a, inv_mask)
    
    img.putalpha(new_a)
    
    # メモリ解放
    del r, g, b, a, mask_r, mask_g, mask_b, combined_mask, inv_mask
    return img

def convert_pdf_sequentially(pdf_path, dpi, is_transparent, zip_file, base_name):
    """
    1ページずつ読み込み→処理→保存→メモリ破棄。
    これによりサーバーのメモリ不足を防ぎます。
    """
    try:
        info = pdfinfo_from_path(pdf_path)
        total_pages = info["Pages"]
        processed_count = 0
        
        # 安全のため15ページ上限（必要に応じて変更可）
        for p in range(1, min(total_pages, 15) + 1):
            # メモリ節約の鍵：thread_count=1 で1ページだけ読み込む
            pages = convert_from_path(pdf_path, dpi=dpi, first_page=p, last_page=p, thread_count=1)
            if not pages: continue
            
            img = pages[0]
            if is_transparent:
                img = make_transparent_robust(img)
            else:
                img = img.convert("RGB")
            
            img_io = io.BytesIO()
            # optimize=FalseでCPU負荷を下げて高速化
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
    
    # パスワードがない場合のみ制限チェック
    if not is_pro:
        now = time.time()
        if ip not in usage_tracker: usage_tracker[ip] = {"count": 0, "reset": now}
        if now - usage_tracker[ip]["reset"] > 86400: usage_tracker[ip] = {"count": 0, "reset": now}
        
        if usage_tracker[ip]["count"] + len(valid_files) > DAILY_LIMIT:
            return jsonify({"error": f"無料枠(1日{DAILY_LIMIT}ファイル)を超えました。パスワードを入力してください。"}), 403

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
            return jsonify({"error": "画像の生成に失敗しました。PDFが空か、解析できません。"}), 500

        # 成功時のみカウントアップ
        if not is_pro:
            usage_tracker[ip]["count"] += len(valid_files)
        
        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name="materials.zip")

    except Exception as e:
        # エラー発生時も必ずJSONを返す（HTMLエラー画面防止）
        return jsonify({"error": f"サーバーエラー: {str(e)}"}), 500
    finally:
        force_cleanup()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
