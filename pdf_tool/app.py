import os, uuid, zipfile, io, gc, time
from flask import Flask, request, render_template, send_file, jsonify
from pdf2image import convert_from_path

app = Flask(__name__)
# 最大アップロードサイズ 50MB
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
UPLOAD_FOLDER = 'temp_storage'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==========================================
# 設定エリア
# ==========================================
PRO_PASSWORD = "your_secret_password"  # あなただけが知る（または販売する）パスワード
FREE_LIMIT = 3                         # 1日の無料制限回数
usage_tracker = {}                     # IPごとの利用回数記録用辞書
# ==========================================

def get_client_ip():
    """ユーザーのグローバルIPアドレスを取得"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0]
    return request.remote_addr

def check_usage_limit(ip):
    """24時間以内の利用回数をチェック"""
    now = time.time()
    if ip not in usage_tracker:
        usage_tracker[ip] = {"count": 0, "last_reset": now}
    
    # 24時間経過していたらカウントリセット
    if now - usage_tracker[ip]["last_reset"] > 86400:
        usage_tracker[ip] = {"count": 0, "last_reset": now}
    
    return usage_tracker[ip]["count"]

def process_pdf_to_zip(pdf_path, dpi, is_transparent, zip_file, base_filename):
    """メモリを極限まで節約しながら逐次ZIP書き出し"""
    try:
        # thread_count=1でメモリ消費を抑制
        pages = convert_from_path(pdf_path, dpi=dpi, thread_count=1)
        for i, page in enumerate(pages[:15]): # 1ファイル最大15ページ
            if is_transparent:
                page = page.convert("RGBA")
                datas = page.getdata()
                # 透過処理
                new_data = [(255, 255, 255, 0) if d[0]>240 and d[1]>240 and d[2]>240 else d for d in datas]
                page.putdata(new_data)
            else:
                page = page.convert("RGB")
            
            # 画像をメモリに溜めず、即ZIPへ書き込む
            img_io = io.BytesIO()
            page.save(img_io, format='PNG', optimize=False)
            zip_file.writestr(f"{base_filename}_{i+1:03d}.png", img_io.getvalue())
            
            # 1ページごとにメモリ解放
            img_io.close()
            page.close()
            del page
            
        del pages
        gc.collect() # ガベージコレクション強制実行
        return True
    except Exception as e:
        print(f"Conversion Error: {e}")
        return False

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    user_ip = get_client_ip()
    user_password = request.form.get('password', '')
    
    # パスワード認証（一致すればPro扱い）
    is_pro = (user_password == PRO_PASSWORD)
    
    # 無料ユーザーの回数制限チェック
    if not is_pro:
        current_usage = check_usage_limit(user_ip)
        if current_usage >= FREE_LIMIT:
            return jsonify({
                "error": "本日の無料枠（3回）を使い切りました。パスワードを入力すれば無制限で利用可能です。",
                "limit_reached": True
            }), 403

    try:
        files = request.files.getlist('file')
        if not files or files[0].filename == '':
            return jsonify({"error": "ファイルが選択されていません"}), 400

        dpi = int(request.form.get('dpi', 150))
        is_transparent = 'transparent' in request.form
        
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as master_zip:
            count = 0
            for file in files:
                if count >= 20: break # 最大20ファイル制限
                if file.filename.lower().endswith('.pdf'):
                    count += 1
                    tmp_id = str(uuid.uuid4())
                    tmp_path = os.path.join(UPLOAD_FOLDER, f"{tmp_id}.pdf")
                    file.save(tmp_path)
                    
                    process_pdf_to_zip(tmp_path, dpi, is_transparent, master_zip, os.path.splitext(file.filename)[0])
                    
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)

        # 成功後、無料ユーザーのみカウント加算
        if not is_pro:
            usage_tracker[user_ip]["count"] += 1
        
        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name="materials.zip")

    except Exception as e:
        return jsonify({"error": f"システムエラー: {str(e)}"}), 500

if __name__ == '__main__':
    # サーバー起動（Render等の環境では環境変数からポートを取得）
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
