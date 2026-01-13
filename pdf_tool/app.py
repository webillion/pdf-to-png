import os
import uuid
import zipfile
import io
import gc
import time
import traceback
from flask import Flask, request, render_template, send_file, jsonify
from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image, ImageChops

app = Flask(__name__)
# Renderの書き込み可能領域
UPLOAD_FOLDER = '/tmp'

# --- ビジネスロジック設定 ---
ADMIN_PASS = "admin1234"      # 開発者用
PRO_PASS = "pro_user_77"      # 一般ユーザー用
FREE_LIMIT = 3                # 無料制限回数

# 簡易的な利用回数管理（メモリ保持）
usage_tracker = {}

def force_cleanup():
    """メモリをOSに強制返却し、Renderの強制終了(SIGKILL)を防止する"""
    gc.collect()
    time.sleep(0.05)

def make_transparent_fast(image):
    """ピクセルループを排除した高速透過演算"""
    img = image.convert("RGBA")
    r, g, b, a = img.split()
    # 245以上の白をマスク化
    mask = r.point(lambda x: 255 if x > 245 else 0)
    mask = ImageChops.multiply(mask, g.point(lambda x: 255 if x > 245 else 0))
    mask = ImageChops.multiply(mask, b.point(lambda x: 255 if x > 245 else 0))
    inv_mask = ImageChops.invert(mask)
    new_a = ImageChops.multiply(a, inv_mask)
    img.putalpha(new_a)
    del r, g, b, a, mask, inv_mask, new_a
    return img

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    force_cleanup()
    
    # 1. 認証とIP取得
    pwd = request.form.get('password', '')
    is_pro = (pwd in [ADMIN_PASS, PRO_PASS])
    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0]
    
    # 2. 回数制限チェック
    if not is_pro:
        current_count = usage_tracker.get(ip, 0)
        if current_count >= FREE_LIMIT:
            return jsonify({
                "status": "locked",
                "error": "本日の無料枠（3回）を超えました。これ以降は有料ライセンス（パスワード）が必要です。"
            }), 403

    # 3. ファイル取得
    files = request.files.getlist('file')
    if not files or files[0].filename == '':
        return jsonify({"error": "PDFファイルを選択してください。"}), 400

    dpi = int(request.form.get('dpi', 150))
    is_transparent = 'transparent' in request.form
    zip_buffer = io.BytesIO()
    
    try:
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as master_zip:
            for f in files:
                if not f.filename.lower().endswith('.pdf'): continue
                
                # 安全な一時保存（xrefエラー対策）
                tmp_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.pdf")
                f.save(tmp_path)
                
                try:
                    info = pdfinfo_from_path(tmp_path)
                    base_name = os.path.splitext(f.filename)[0]
                    
                    for p in range(1, info["Pages"] + 1):
                        # 【重要】1ページずつCairoエンジンで展開し、即座に画像化
                        pages = convert_from_path(
                            tmp_path, dpi=dpi, first_page=p, last_page=p,
                            use_pdftocairo=True, thread_count=1
                        )
                        if not pages: continue
                        
                        img = pages[0]
                        if is_transparent:
                            img = make_transparent_fast(img)
                        
                        # ZIPへストリーム書き込み
                        img_io = io.BytesIO()
                        img.save(img_io, format='PNG')
                        master_zip.writestr(f"{base_name}_p{p:03d}.png", img_io.getvalue())
                        
                        # 即時解放サイクル
                        img.close()
                        img_io.close()
                        del img, pages
                        force_cleanup()
                finally:
                    if os.path.exists(tmp_path): os.remove(tmp_path)
        
        # 成功時にカウントアップ
        if not is_pro:
            usage_tracker[ip] = usage_tracker.get(ip, 0) + 1
        
        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name="materials.zip")

    except Exception as e:
        return jsonify({"error": f"システムエラー: {str(e)}"}), 500
    finally:
        force_cleanup()

@app.route('/status', methods=['GET'])
def get_status():
    """現在の利用回数をフロントに返す"""
    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0]
    return jsonify({"count": usage_tracker.get(ip, 0), "limit": FREE_LIMIT})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
