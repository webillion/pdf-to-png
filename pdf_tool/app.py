import os
import uuid
import time
import zipfile
import io
import psutil
from flask import Flask, request, render_template, send_file, after_this_request, make_response
from pdf2image import convert_from_path
from PIL import Image

app = Flask(__name__)

# 最大アップロードサイズ（合計30MB制限）
app.config['MAX_CONTENT_LENGTH'] = 30 * 1024 * 1024
UPLOAD_FOLDER = 'temp_storage'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def cleanup_old_files():
    """古い一時ファイルを削除"""
    now = time.time()
    for filename in os.listdir(UPLOAD_FOLDER):
        path = os.path.join(UPLOAD_FOLDER, filename)
        try:
            if os.path.getmtime(path) < now - 600:
                os.remove(path)
        except Exception:
            pass

@app.route('/', methods=['GET', 'POST'])
def index():
    cleanup_old_files()
    if request.method == 'POST':
        # 複数ファイルを取得
        files = request.files.getlist('file')
        if not files or files[0].filename == '':
            return "ファイルが選択されていません", 400

        selected_dpi = int(request.form.get('dpi', 150))
        is_transparent = 'transparent' in request.form
        
        zip_buffer = io.BytesIO()
        
        try:
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for file in files:
                    if not file.filename.lower().endswith('.pdf'):
                        continue

                    unique_id = str(uuid.uuid4())
                    pdf_path = os.path.join(UPLOAD_FOLDER, f"{unique_id}.pdf")
                    file.save(pdf_path)

                    # 1ファイルあたり最大20ページに制限（負荷対策）
                    pages = convert_from_path(pdf_path, dpi=selected_dpi)
                    pages = pages[:20] 

                    # ファイル名をフォルダ名にする
                    folder_name = os.path.splitext(file.filename)[0]

                    for i, page in enumerate(pages):
                        if is_transparent:
                            page = page.convert("RGBA")
                            datas = page.getdata()
                            # 透過アルゴリズム（白背景除去）
                            new_data = [(255, 255, 255, 0) if d[0]>240 and d[1]>240 and d[2]>240 else d for d in datas]
                            page.putdata(new_data)
                        else:
                            page = page.convert("RGB")

                        img_io = io.BytesIO()
                        page.save(img_io, format='PNG', optimize=True)
                        
                        # ZIP内パス: "PDF名/material_001.png"
                        zip_path = f"{folder_name}/material_{i+1:03d}.png"
                        zip_file.writestr(zip_path, img_io.getvalue())
                    
                    # 変換後、即座にPDFを削除
                    if os.path.exists(pdf_path):
                        os.remove(pdf_path)

            zip_buffer.seek(0)
            
            response = make_response(send_file(
                zip_buffer,
                mimetype='application/zip',
                as_attachment=True,
                download_name=f'bulk_material_{int(time.time())}.zip'
            ))
            response.set_cookie('download_started', 'true', path='/')
            return response

        except Exception as e:
            return f"エラーが発生しました: {str(e)}", 500

    return render_template('index.html')

@app.route('/debug-files')
def health_check():
    memory = psutil.virtual_memory()
    return render_template('debug.html', memory=memory, files=os.listdir(UPLOAD_FOLDER))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
