import os
import uuid
import time
import zipfile
import io
import psutil
from flask import Flask, request, render_template, send_file, after_this_request
from pdf2image import convert_from_path
from PIL import Image

app = Flask(__name__)

# 最大アップロードサイズ: 20MB
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024
UPLOAD_FOLDER = 'temp_storage'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def cleanup_old_files():
    """10分以上経過した古いPDFファイルを削除（サーバー容量保護）"""
    now = time.time()
    for filename in os.listdir(UPLOAD_FOLDER):
        path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.getmtime(path) < now - 600:
            if os.path.isfile(path):
                os.remove(path)

@app.route('/', methods=['GET', 'POST'])
def index():
    cleanup_old_files()
    if request.method == 'POST':
        if 'file' not in request.files:
            return "ファイルがありません", 400
        
        file = request.files['file']
        if file.filename == '':
            return "ファイルが選択されていません", 400

        # ユーザー設定の取得
        selected_dpi = int(request.form.get('dpi', 150))
        is_transparent = 'transparent' in request.form
        
        # 一時的なPDF保存
        unique_id = str(uuid.uuid4())
        pdf_path = os.path.join(UPLOAD_FOLDER, f"{unique_id}.pdf")
        file.save(pdf_path)

        try:
            # サーバー負荷対策：高画質(300DPI)なら10ページ、それ以外なら50ページまでに制限
            max_p = 10 if selected_dpi > 200 else 50
            pages = convert_from_path(pdf_path, dpi=selected_dpi)
            pages = pages[:max_p]

            # ZIPファイルをメモリ上で作成
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for i, page in enumerate(pages):
                    
                    if is_transparent:
                        # 背景透過処理
                        page = page.convert("RGBA")
                        datas = page.getdata()
                        new_data = []
                        for item in datas:
                            # 白に近い色（240以上）を透明に置換
                            if item[0] > 240 and item[1] > 240 and item[2] > 240:
                                new_data.append((255, 255, 255, 0))
                            else:
                                new_data.append(item)
                        page.putdata(new_data)
                    else:
                        page = page.convert("RGB")

                    # メモリ内に画像を書き出し
                    img_io = io.BytesIO()
                    page.save(img_io, format='PNG', optimize=True)
                    # 動画編集ソフトで扱いやすい「001」形式の連番
                    filename = f"video_material_{i+1:03d}.png"
                    zip_file.writestr(filename, img_io.getvalue())

            zip_buffer.seek(0)

            # 送信後に元のPDFを物理削除
            @after_this_request
            def remove_file(response):
                try:
                    if os.path.exists(pdf_path):
                        os.remove(pdf_path)
                except Exception as e:
                    app.logger.error(f"Error removing file: {e}")
                return response

            return send_file(
                zip_buffer,
                mimetype='application/zip',
                as_attachment=True,
                download_name=f'converted_material_{selected_dpi}dpi.zip'
            )

        except Exception as e:
            return f"変換エラー: {str(e)}。ファイルが大きすぎるか、メモリ制限に達した可能性があります。", 500

    return render_template('index.html')

@app.route('/debug-files')
def health_check():
    """サーバーの負荷状況を監視するページ"""
    memory = psutil.virtual_memory()
    files = os.listdir(UPLOAD_FOLDER)
    return render_template('debug.html', memory=memory, files=files)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
