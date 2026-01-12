import os, uuid, zipfile, io, gc, time
from flask import Flask, request, render_template, send_file, jsonify
from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image

app = Flask(__name__)
# Render等の無料サーバーでは /tmp フォルダを使用するのが鉄則です
UPLOAD_FOLDER = '/tmp/material_studio'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==========================================
# 【設定】パスワードと制限
# ==========================================
DEV_PASS = "admin1234"      # あなた（開発者）用
USER_PASS = "pro_user_77"   # 販売・配布用
DAILY_FILE_LIMIT = 3        # 一般ユーザーの1日上限
usage_tracker = {}          # {IP: {"count": 0, "reset": timestamp}}

def force_cleanup():
    """Pythonのゴミ拾い(GC)を強制実行し、メモリをOSに返却しやすくする"""
    gc.collect()
    time.sleep(0.1)

def get_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0]

def check_limit(ip, count):
    now = time.time()
    if ip not in usage_tracker:
        usage_tracker[ip] = {"count": 0, "reset": now}
    # 24時間経過でリセット
    if now - usage_tracker[ip]["reset"] > 86400:
        usage_tracker[ip] = {"count": 0, "reset": now}
    return usage_tracker[ip]["count"] + count <= DAILY_FILE_LIMIT

def make_transparent_optimized(image):
    """ピクセルループを回避し、メモリ負荷を抑えて白背景を抜く"""
    img = image.convert("RGBA")
    r, g, b, a = img.split()
    # 245以上の白をマスク。255固定よりスキャンデータ等に強い
    mask = Image.eval(lambda r_v, g_v, b_v: 255 if r_v > 245 and g_v > 245 and b_v > 245 else 0, r, g, b)
    new_a = Image.eval(lambda a_v, m_v: 0 if m_v == 255 else a_v, a, mask)
    img.putalpha(new_a)
    del r, g, b, a, mask
    return img

def convert_pdf_sequentially(pdf_path, dpi, is_transparent, zip_file, base_name):
    """
    1ページずつ読み込み→処理→保存を繰り返す。
    全ページ一括読み込みをしないため、メモリ消費が常に1ページ分で済みます。
    """
    try:
        info = pdfinfo_from_path(pdf_path)
        total_pages = info["Pages"]
        processed_count = 0
        
        # 安全のため最大15ページまでに制限（必要なら変更可）
        for p in range(1, min(total_pages, 15) + 1):
            pages = convert_from_path(pdf_path, dpi=dpi, first_page=p, last_page=p, thread_count=1)
            if not pages: continue
            
            img = pages[0]
            if is_transparent:
                img = make_transparent_optimized(img)
            else:
                img = img.convert("RGB")
            
            img_io = io.BytesIO()
            img.save(img_io, format='PNG', optimize=False)
            zip_file.writestr(f"{base_name}_{p:03d}.png", img_io.getvalue())
            
            # ページごとにメモリを徹底解放
            img_io.close()
            img.close()
            del img, pages
            force_cleanup()
            processed_count += 1
            
        return processed_count
    except Exception as e:
        print(f"Error: {e}")
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
    ip = get_ip()
    
    files = request.files.getlist('file')
    valid_files = [f for f in files if f.filename.lower().endswith('.pdf')]
    
    if not is_pro:
        if not check_limit(ip, len(valid_files)):
            return jsonify({"error": "1日の無料枠を超えました。パスワードを入力してください。"}), 403

    try:
        dpi = int(request.form.get('dpi', 150))
        is_transparent = 'transparent' in request.form
        zip_buffer = io.BytesIO()
        total_images = 0
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as master_zip:
            for f in valid_files:
                tmp_name = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.pdf")
                f.save(tmp_name)
                
                # 逐次変換実行
                count = convert_pdf_sequentially(tmp_name, dpi, is_transparent, master_zip, os.path.splitext(f.filename)[0])
                total_images += count
                
                if os.path.exists(tmp_name): os.remove(tmp_name)
                force_cleanup()

        if total_images == 0:
            return jsonify({"error": "変換に失敗しました。PDFが空か、解析不能です。"}), 500

        if not is_pro:
            usage_tracker[ip]["count"] += len(valid_files)
        
        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name="materials.zip")

    except Exception as e:
        return jsonify({"error": f"サーバーメモリ限界です。画質を下げるか1枚ずつ試してください。({str(e)})"}), 500
    finally:
        force_cleanup()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
