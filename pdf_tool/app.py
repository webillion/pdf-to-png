import os
import time
import uuid
from flask import Flask, render_template, request
from pdf2image import convert_from_path

app = Flask(__name__)

# --- 設定 ---
UPLOAD_FOLDER = 'static'
# アップロードサイズを16MBに制限（サーバー保護）
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 

# 保存先フォルダがなければ作成
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def cleanup_old_files():
    """10分以上経過したファイルを削除するお掃除関数"""
    now = time.time()
    if not os.path.exists(UPLOAD_FOLDER):
        return
    
    for filename in os.listdir(UPLOAD_FOLDER):
        # 変換したPNGと一時PDFを対象にする
        if filename.endswith(".png") or filename.endswith(".pdf"):
            path = os.path.join(UPLOAD_FOLDER, filename)
            # 600秒（10分）以上前のファイルを削除
            if os.path.getmtime(path) < now - 600:
                try:
                    os.remove(path)
                except Exception as e:
                    print(f"Error deleting {filename}: {e}")

# --- デバッグ用ページ（監視機能） ---
@app.route('/debug-files')
def list_files():
    """現在のサーバー内のファイル状況を表示する"""
    files = []
    total_size = 0
    now = time.time()
    
    if os.path.exists(UPLOAD_FOLDER):
        for filename in os.listdir(UPLOAD_FOLDER):
            path = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.isfile(path):
                size = os.path.getsize(path) / 1024  # KB
                mtime = os.path.getmtime(path)
                age = int((now - mtime) / 60)  # 分
                files.append({
                    'name': filename,
                    'size': f"{size:.1f} KB",
                    'age': f"{age} min ago"
                })
                total_size += size

    # シンプルなHTMLで結果を表示
    output = f"<h1>Server Storage Status</h1>"
    output += f"<p><strong>Total Files:</strong> {len(files)}</p>"
    output += f"<p><strong>Total Size:</strong> {total_size/1024:.2f} MB</p>"
    output += "<table border='1' style='border-collapse: collapse; width: 100%;'>"
    output += "<tr><th>File Name</th><th>Size</th><th>Created</th></tr>"
    for f in files:
        output += f"<tr><td>{f['name']}</td><td>{f['size']}</td><td>{f['age']}</td></tr>"
    output += "</table>"
    output += "<br><a href='/'>Back to Home</a>"
    
    return output

# --- メインページ（変換機能） ---
@app.route('/', methods=['GET', 'POST'])
def index():
    # アクセスがあるたびにお掃除を実行
    cleanup_old_files()
    
    images = []
    if request.method == 'POST':
        pdf_file = request.files.get('file')
        
        if pdf_file and pdf_file.filename:
            # 1. 重複しない名前を作成
            unique_id = str(uuid.uuid4())
            pdf_path = os.path.join(UPLOAD_FOLDER, f"{unique_id}.pdf")
            pdf_file.save(pdf_path)

            try:
                # 2. PDFを画像に変換 (dpi=100でメモリ節約)
                pages = convert_from_path(pdf_path, dpi=100)
                
                # 3. 画像を保存
                for i, page in enumerate(pages):
                    img_name = f"{unique_id}_{i}.png"
                    img_path = os.path.join(UPLOAD_FOLDER, img_name)
                    page.save(img_path, "PNG")
                    images.append(img_name)
                
                # 4. PDFはその場で削除
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)
                    
            except Exception as e:
                return f"変換エラー: {e}"

    return render_template('index.html', images=images)

if __name__ == '__main__':
    app.run(debug=True)
