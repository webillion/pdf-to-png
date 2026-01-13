import os
import uuid
import zipfile
import io
import gc
import time
import logging
import traceback
from datetime import datetime
from flask import Flask, request, render_template, send_file, jsonify
from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image, ImageChops

# --- ロギング設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
# Renderの書き込み可能領域
UPLOAD_FOLDER = '/tmp'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB制限

# --- 定数・制限設定 ---
ADMIN_PASS = "admin1234"
PRO_PASS = "pro_user_77"
FREE_LIMIT = 3
usage_tracker = {}  # IPベースの利用回数管理

def force_cleanup():
    """メモリをOSに強制返却。300DPI処理には必須"""
    gc.collect()
    time.sleep(0.05)

def make_transparent_perfect(image):
    """
    ピクセルループを使わない高速透過。
    300DPIの大容量画像でもメモリを消費せず一瞬で白を抜きます。
    """
    img = image.convert("RGBA")
    r, g, b, a = img.split()
    # 245以上の明るさを白と判定
    mask = r.point(lambda x: 255 if x > 245 else 0)
    mask = ImageChops.multiply(mask, g.point(lambda x: 255 if x > 245 else 0))
    mask = ImageChops.multiply(mask, b.point(lambda x: 255 if x > 245 else 0))
    inv_mask = ImageChops.invert(mask)
    new_a = ImageChops.multiply(a, inv_mask)
    img.putalpha(new_a)
    del r, g, b, a, mask, inv_mask, new_a
    return img

def get_client_ip():
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0]
    return request.remote_addr

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/status', methods=['GET'])
def check_status():
    ip = get_client_ip()
    count = usage_tracker.get(ip, 0)
    return jsonify({
        "ip": ip,
        "count": count,
        "limit": FREE_LIMIT
    })

@app.route('/convert', methods=['POST'])
def convert():
    force_cleanup()
    start_time = time.time()
    
    # 1. 認証と制限チェック
    pwd = request.form.get('password', '')
    is_pro = (pwd in [ADMIN_PASS, PRO_PASS])
    ip = get_client_ip()
    
    if not is_pro:
        current_count = usage_tracker.get(ip, 0)
        if current_count >= FREE_LIMIT:
            logger.warning(f"Locked: {ip}")
            return jsonify({
                "status": "locked",
                "error": "無料枠（3回）を超えました。これ以上はパスワードが必要です。"
            }), 403

    # 2. ファイル取得
    files = request.files.getlist('file')
    if not files or files[0].filename == '':
        return jsonify({"error": "ファイルがありません。"}), 400

    dpi = int(request.form.get('dpi', 150))
    is_transparent = 'transparent' in request.form
    zip_buffer = io.BytesIO()
    
    try:
        logger.info(f"Start: IP={ip}, DPI={dpi}")
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as master_zip:
            for f in files:
                if not f.filename.lower().endswith('.pdf'): continue
                
                # 安全な一時保存（xrefエラー対策）
                tmp_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.pdf")
                f.save(tmp_path)
                
                try:
                    info = pdfinfo_from_path(tmp_path)
                    total_pages = info["Pages"]
                    base_name = os.path.splitext(f.filename)[0]
                    
                    for p in range(1, total_pages + 1):
                        # 300DPI対策：1ページずつCairoで処理
                        pages = convert_from_path(
                            tmp_path, dpi=dpi, first_page=p, last_page=p,
                            use_pdftocairo=True, thread_count=1
                        )
                        if not pages: continue
                        
                        img = pages[0]
                        if is_transparent:
                            img = make_transparent_perfect(img)
                        
                        img_io = io.BytesIO()
                        img.save(img_io, format='PNG', optimize=False)
                        master_zip.writestr(f"{base_name}_{p:03d}.png", img_io.getvalue())
                        
                        # 徹底したメモリ解放
                        img.close()
                        img_io.close()
                        del img, pages
                        force_cleanup()
                        
                    logger.info(f"Done: {f.filename}")
                finally:
                    if os.path.exists(tmp_path): os.remove(tmp_path)

        if not is_pro:
            usage_tracker[ip] = usage_tracker.get(ip, 0) + 1

        zip_buffer.seek(0)
        return send_file(
            zip_buffer, 
            mimetype='application/zip', 
            as_attachment=True, 
            download_name=f"materials_{datetime.now().strftime('%H%M%S')}.zip"
        )

    except Exception as e:
        logger.error(traceback.format_exc())
        return jsonify({"error": f"システムエラー: {str(e)}"}), 500
    finally:
        force_cleanup()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
