import os, uuid, zipfile, io, gc, time, traceback
from flask import Flask, request, render_template, send_file, jsonify
from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image, ImageChops

app = Flask(__name__)
UPLOAD_FOLDER = '/tmp'

# --- 認証・制限設定 ---
ADMIN_PASS = "admin1234"      # 開発者用
PRO_PASS = "pro_user_77"      # 一般ユーザー用
FREE_LIMIT = 3                # 無料枠（ファイル数）
usage_tracker = {}

def force_cleanup():
    gc.collect()
    time.sleep(0.1)

def make_transparent_perfect(image):
    """PNG展開後の透過処理（低メモリ演算）"""
    img = image.convert("RGBA")
    r, g, b, a = img.split()
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
    
    pwd = request.form.get('password', '')
    is_pro = (pwd in [ADMIN_PASS, PRO_PASS])
    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0]
    
    if not is_pro:
        if ip not in usage_tracker: usage_tracker[ip] = 0
        if usage_tracker[ip] >= FREE_LIMIT:
            return jsonify({
                "status": "locked",
                "error": f"1日の無料枠（{FREE_LIMIT}回）を超えました。継続利用にはパスワードを入力してください。"
            }), 403

    files = request.files.getlist('file')
    if not files or files[0].filename == '':
        return jsonify({"error": "ファイルが選択されていません。"}), 400

    dpi = int(request.form.get('dpi', 150))
    is_transparent = 'transparent' in request.form
    zip_buffer = io.BytesIO()
    
    try:
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as master_zip:
            for f in files:
                if f.filename == '': continue
                
                tmp_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.pdf")
                f.save(tmp_path)
                
                try:
                    info = pdfinfo_from_path(tmp_path)
                    base_name = os.path.splitext(f.filename)[0]
                    
                    for p in range(1, info["Pages"] + 1):
                        pages = convert_from_path(
                            tmp_path, dpi=dpi, first_page=p, last_page=p,
                            use_pdftocairo=True, thread_count=1
                        )
                        if not pages: continue
                        img = pages[0]
                        if is_transparent:
                            img = make_transparent_perfect(img)
                        
                        img_io = io.BytesIO()
                        img.save(img_io, format='PNG')
                        master_zip.writestr(f"{base_name}_{p:03d}.png", img_io.getvalue())
                        
                        img.close()
                        img_io.close()
                        del img, pages
                        force_cleanup()
                    
                    if not is_pro: usage_tracker[ip] += 1
                        
                finally:
                    if os.path.exists(tmp_path): os.remove(tmp_path)

        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name="materials.zip")

    except Exception as e:
        return jsonify({"error": f"エラー: {str(e)}"}), 500
