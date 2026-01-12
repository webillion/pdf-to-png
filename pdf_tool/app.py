import os, uuid, zipfile, io, gc, time
from flask import Flask, request, render_template, send_file, jsonify
from pdf2image import convert_from_path
from PIL import Image

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
UPLOAD_FOLDER = 'temp_storage'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==========================================
# 設定エリア
# ==========================================
PRO_PASSWORD = "your_secret_password"
FILE_DAILY_LIMIT = 3
usage_tracker = {}

def get_client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0]

def check_usage_limit(ip):
    now = time.time()
    if ip not in usage_tracker:
        usage_tracker[ip] = {"file_count": 0, "last_reset": now}
    if now - usage_tracker[ip]["last_reset"] > 86400:
        usage_tracker[ip] = {"file_count": 0, "last_reset": now}
    return usage_tracker[ip]["file_count"]

def make_transparent_fast(image):
    """
    メモリ消費を抑えた高速透過ロジック。
    getdata()による巨大なリスト作成を避け、マスク処理を使用。
    """
    img = image.convert("RGBA")
    # 各チャンネルに分解
    r, g, b, a = img.split()
    
    # 250以上の明るさ（ほぼ白）を判定するマスクを作成
    # (R > 250) & (G > 250) & (B > 250)
    mask_r = r.point(lambda x: 255 if x > 250 else 0, '1')
    mask_g = g.point(lambda x: 255 if x > 250 else 0, '1')
    mask_b = b.point(lambda x: 255 if x > 250 else 0, '1')
    
    # 三つの色が全て白い部分を特定
    white_mask = Image.eval(lambda r_v, g_v, b_v: 255 if r_v and g_v and b_v else 0, mask_r, mask_g, mask_b)
    
    # 白い部分のアルファチャンネルを0（透明）に書き換える
    new_a = Image.eval(lambda a_v, m_v: 0 if m_v else a_v, a, white_mask)
    
    # チャンネルを再合成
    img.putalpha(new_a)
    return img

def process_pdf_to_zip(pdf_path, dpi, is_transparent, zip_file, base_filename):
    try:
        # thread_count=1 でCPU負荷とメモリを抑える
        pages = convert_from_path(pdf_path, dpi=dpi, thread_count=1)
        for i, page in enumerate(pages[:15]):
            if is_transparent:
                # 高速版透過処理を適用
                page = make_transparent_fast(page)
            else:
                page = page.convert("RGB")
            
            img_io = io.BytesIO()
            page.save(img_io, format='PNG', optimize=False)
            zip_file.writestr(f"{base_filename}_{i+1:03d}.png", img_io.getvalue())
            
            img_io.close()
            page.close()
            del page
            
        del pages
        gc.collect()
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    user_ip = get_client_ip()
    user_password = request.form.get('password', '')
    is_pro = (user_password == PRO_PASSWORD)

    files = request.files.getlist('file')
    valid_files = [f for f in files if f.filename != '']
    upload_count = len(valid_files)

    # 1. 無料枠の合計ファイル数制限 (サーバー側)
    if not is_pro:
        current_files = check_usage_limit(user_ip)
        if current_files + upload_count > FILE_DAILY_LIMIT:
            return jsonify({
                "error": f"1日の無料枠を超えています（残り: {max(0, FILE_DAILY_LIMIT - current_files)}ファイル）。パスワードを入力すれば無制限になります。",
                "limit_reached": True
            }), 403

    try:
        dpi = int(request.form.get('dpi', 150))
        is_transparent = 'transparent' in request.form
        
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as master_zip:
            processed_count = 0
            for file in valid_files:
                processed_count += 1
                tmp_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.pdf")
                file.save(tmp_path)
                process_pdf_to_zip(tmp_path, dpi, is_transparent, master_zip, os.path.splitext(file.filename)[0])
                if os.path.exists(tmp_path): os.remove(tmp_path)

        if not is_pro:
            usage_tracker[user_ip]["file_count"] += processed_count
        
        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name="output.zip")

    except Exception as e:
        # エラー時は可能な限りJSONで返す
        return jsonify({"error": f"サーバー負荷エラー: {str(e)}"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
