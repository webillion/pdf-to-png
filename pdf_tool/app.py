import os, uuid, zipfile, io, gc, time
from flask import Flask, request, render_template, send_file, jsonify
from pdf2image import convert_from_path
from PIL import Image

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
UPLOAD_FOLDER = 'temp_storage'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- 設定 ---
DEV_PASS = "dev_admin_key"  # 開発者用
USER_PASS = "user_pro_key"  # 一般ユーザー用
FILE_LIMIT = 3
usage_tracker = {}

def make_transparent_low_mem(image):
    """
    メモリを節約した透過処理。
    巨大なリストを作らずに、各チャンネルを直接操作します。
    """
    img = image.convert("RGBA")
    r, g, b, a = img.split()
    
    # 248以上の白を検知するマスク（閾値は調整済み）
    white_mask = Image.eval(lambda r_v, g_v, b_v: 255 if r_v > 248 and g_v > 248 and b_v > 248 else 0, r, g, b)
    
    # 白い部分だけアルファを0にする
    new_a = Image.eval(lambda a_v, m_v: 0 if m_v == 255 else a_v, a, white_mask)
    img.putalpha(new_a)
    
    # 不要なチャンネルデータを即座に削除
    del r, g, b, a, white_mask
    return img

def process_pdf_to_zip(pdf_path, dpi, is_transparent, zip_file, base_filename):
    success_count = 0
    try:
        # thread_count=1でメモリ爆発を防止
        pages = convert_from_path(pdf_path, dpi=dpi, thread_count=1)
        
        for i, page in enumerate(pages[:15]):
            if is_transparent:
                page = make_transparent_low_mem(page)
            else:
                page = page.convert("RGB")
            
            # 画像をPNG形式のバイナリに変換
            img_io = io.BytesIO()
            page.save(img_io, format='PNG', optimize=False)
            
            # ZIPに即座に書き込み
            zip_file.writestr(f"{base_filename}_{i+1:03d}.png", img_io.getvalue())
            
            # 【重要】処理が終わった瞬間、メモリから消去
            img_io.close()
            page.close()
            del page
            success_count += 1
            
        del pages
        gc.collect() # 掃除屋（ガベージコレクタ）を呼び出す
        return success_count
    except Exception as e:
        print(f"Error: {e}")
        return 0

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0]
    pwd = request.form.get('password', '')
    is_pro = (pwd == DEV_PASS or pwd == USER_PASS)

    files = request.files.getlist('file')
    valid_files = [f for f in files if f.filename != '']
    
    # パスワードがない場合のみ数制限を適用
    if not is_pro:
        now = time.time()
        if user_ip not in usage_tracker: usage_tracker[user_ip] = {"count": 0, "reset": now}
        if now - usage_tracker[user_ip]["reset"] > 86400: usage_tracker[user_ip] = {"count": 0, "reset": now}
        
        if usage_tracker[user_ip]["count"] + len(valid_files) > FILE_LIMIT:
            return jsonify({"error": "1日の制限を超えました。パスワードを入力してください。"}), 403

    try:
        dpi = int(request.form.get('dpi', 150))
        is_transparent = 'transparent' in request.form
        
        zip_buffer = io.BytesIO()
        processed_total = 0
        
        # ZIPファイルをオープン
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as master_zip:
            for file in valid_files:
                tmp_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.pdf")
                file.save(tmp_path)
                processed_total += process_pdf_to_zip(tmp_path, dpi, is_transparent, master_zip, os.path.splitext(file.filename)[0])
                if os.path.exists(tmp_path): os.remove(tmp_path)

        if processed_total == 0:
            return jsonify({"error": "画像の生成に失敗しました。ファイルが重すぎる可能性があります。"}), 500

        if not is_pro:
            usage_tracker[user_ip]["count"] += len(valid_files)
        
        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name="output.zip")

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
