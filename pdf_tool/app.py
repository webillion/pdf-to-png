import os, uuid, time, zipfile, io, psutil
from flask import Flask, request, render_template, send_file, make_response
from pdf2image import convert_from_path

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 30 * 1024 * 1024 # 合計30MB制限
UPLOAD_FOLDER = 'temp_storage'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def process_pdf_to_images(pdf_path, dpi, is_transparent):
    """PDFをPNG画像リストに変換する共通関数"""
    try:
        pages = convert_from_path(pdf_path, dpi=dpi)
        pages = pages[:20]  # 1ファイル20ページ制限
        output_images = []
        for i, page in enumerate(pages):
            if is_transparent:
                page = page.convert("RGBA")
                datas = page.getdata()
                # ユーザーの選択に基づいた透過処理
                new_data = [(255, 255, 255, 0) if d[0]>240 and d[1]>240 and d[2]>240 else d for d in datas]
                page.putdata(new_data)
            else:
                page = page.convert("RGB")
            
            img_io = io.BytesIO()
            page.save(img_io, format='PNG', optimize=True)
            output_images.append((f"_{i+1:03d}.png", img_io.getvalue()))
        return output_images
    except:
        return []

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        files = request.files.getlist('file')
        selected_dpi = int(request.form.get('dpi', 150))
        is_transparent = 'transparent' in request.form # ユーザーの選択を取得
        
        all_converted_data = [] # (zip_internal_path, data)

        for file in files:
            filename_low = file.filename.lower()
            
            # --- 複数ファイル/ZIP内のPDFを処理 ---
            if filename_low.endswith('.zip'):
                with zipfile.ZipFile(file, 'r') as ref_zip:
                    for z_info in ref_zip.infolist():
                        # ディレクトリそのものはスキップ
                        if z_info.is_dir(): continue
                        
                        if z_info.filename.lower().endswith('.pdf'):
                            with ref_zip.open(z_info) as z_file:
                                tmp_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.pdf")
                                with open(tmp_path, "wb") as f: f.write(z_file.read())
                                
                                images = process_pdf_to_images(tmp_path, selected_dpi, is_transparent)
                                # 元のパスから拡張子を除去してベースパスを作成（フォルダ構造を維持）
                                base_path = os.path.splitext(z_info.filename)[0]
                                for suffix, data in images:
                                    all_converted_data.append((base_path + suffix, data))
                                
                                if os.path.exists(tmp_path): os.remove(tmp_path)
            
            elif filename_low.endswith('.pdf'):
                tmp_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.pdf")
                file.save(tmp_path)
                images = process_pdf_to_images(tmp_path, selected_dpi, is_transparent)
                base_path = os.path.splitext(file.filename)[0]
                for suffix, data in images:
                    all_converted_data.append((base_path + suffix, data))
                
                if os.path.exists(tmp_path): os.remove(tmp_path)

        if not all_converted_data:
            return "PDFファイルが見つからないか、変換に失敗しました。", 400

        # --- 動的なレスポンス出力 ---
        
        # 1. 成果物が1枚だけならPNGとして直接ダウンロード
        if len(all_converted_data) == 1:
            path, data = all_converted_data[0]
            download_name = os.path.basename(path)
            response = make_response(send_file(io.BytesIO(data), mimetype='image/png', as_attachment=True, download_name=download_name))
            response.set_cookie('download_started', 'true', path='/')
            return response

        # 2. 成果物が複数ならZIPにまとめてダウンロード（フォルダ階層を維持）
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for path, data in all_converted_data:
                zip_file.writestr(path, data)
        
        zip_buffer.seek(0)
        response = make_response(send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name="converted_assets.zip"))
        response.set_cookie('download_started', 'true', path='/')
        return response

    return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
