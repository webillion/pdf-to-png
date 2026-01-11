import os, uuid, time, zipfile, io, psutil
from flask import Flask, request, render_template, send_file, make_response
from pdf2image import convert_from_path

app = Flask(__name__)
# 合計40MBまでのアップロードを許可
app.config['MAX_CONTENT_LENGTH'] = 40 * 1024 * 1024
UPLOAD_FOLDER = 'temp_storage'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def process_pdf_to_images(pdf_path, dpi, is_transparent):
    """PDFをPNG画像に変換し、(ファイル名, バイナリ)のリストを返す"""
    try:
        pages = convert_from_path(pdf_path, dpi=dpi)
        # 【制限事項】1ファイルあたり最大15ページまでに制限（Render無料枠のメモリ保護のため）
        pages = pages[:15] 
        output_images = []
        for i, page in enumerate(pages):
            if is_transparent:
                page = page.convert("RGBA")
                datas = page.getdata()
                # 透過処理（白背景除去）
                new_data = [(255, 255, 255, 0) if d[0]>240 and d[1]>240 and d[2]>240 else d for d in datas]
                page.putdata(new_data)
            else:
                page = page.convert("RGB")
            
            img_io = io.BytesIO()
            page.save(img_io, format='PNG', optimize=True)
            output_images.append((f"_{i+1:03d}.png", img_io.getvalue()))
        return output_images
    except Exception as e:
        print(f"Conversion error: {e}")
        return []

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        files = request.files.getlist('file')
        selected_dpi = int(request.form.get('dpi', 150))
        is_transparent = 'transparent' in request.form
        
        all_converted_data = []
        total_pdf_count = 0
        MAX_PDF_LIMIT = 20

        # --- 事前チェック：合計PDF数をカウント ---
        for file in files:
            if file.filename.lower().endswith('.pdf'):
                total_pdf_count += 1
            elif file.filename.lower().endswith('.zip'):
                with zipfile.ZipFile(file, 'r') as ref_zip:
                    pdfs_in_zip = [z for z in ref_zip.infolist() if not z.is_dir() and z.filename.lower().endswith('.pdf')]
                    total_pdf_count += len(pdfs_in_zip)
        
        if total_pdf_count > MAX_PDF_LIMIT:
            return f"エラー: 合計ファイル数が制限（{MAX_PDF_LIMIT}個）を超えています。", 400

        # --- 変換処理開始 ---
        for file in files:
            filename_low = file.filename.lower()
            
            if filename_low.endswith('.zip'):
                file_bytes = file.read()
                with zipfile.ZipFile(io.BytesIO(file_bytes), 'r') as ref_zip:
                    for z_info in ref_zip.infolist():
                        if z_info.is_dir() or not z_info.filename.lower().endswith('.pdf'):
                            continue
                        
                        with ref_zip.open(z_info) as z_file:
                            tmp_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.pdf")
                            with open(tmp_path, "wb") as f: f.write(z_file.read())
                            
                            images = process_pdf_to_images(tmp_path, selected_dpi, is_transparent)
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
            return "変換可能なPDFが見つかりませんでした。", 400

        # --- レスポンス生成 ---
        if len(all_converted_data) == 1:
            path, data = all_converted_data[0]
            download_name = os.path.basename(path)
            response = make_response(send_file(io.BytesIO(data), mimetype='image/png', as_attachment=True, download_name=download_name))
            response.set_cookie('download_started', 'true', path='/')
            return response

        zip_output = io.BytesIO()
        with zipfile.ZipFile(zip_output, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for path, data in all_converted_data:
                zip_file.writestr(path, data)
        
        zip_output.seek(0)
        response = make_response(send_file(zip_output, mimetype='application/zip', as_attachment=True, download_name="converted_assets.zip"))
        response.set_cookie('download_started', 'true', path='/')
        return response

    return render_template('index.html')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
