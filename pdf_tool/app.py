import os, uuid, time, zipfile, io
from flask import Flask, request, render_template, send_file, make_response, jsonify

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 40 * 1024 * 1024 # 40MB
UPLOAD_FOLDER = 'temp_storage'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def process_pdf_to_images(pdf_path, dpi, is_transparent):
    try:
        pages = convert_from_path(pdf_path, dpi=dpi)
        pages = pages[:15] # 15ページ制限
        output_images = []
        for i, page in enumerate(pages):
            if is_transparent:
                page = page.convert("RGBA")
                datas = page.getdata()
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

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    files = request.files.getlist('file')
    if not files or files[0].filename == '':
        return jsonify({"error": "ファイルが選択されていません"}), 400

    selected_dpi = int(request.form.get('dpi', 150))
    is_transparent = 'transparent' in request.form
    
    all_converted_data = []
    total_pdf_count = 0
    MAX_PDF_LIMIT = 20

    try:
        # 1. カウントチェック
        for file in files:
            if file.filename.lower().endswith('.pdf'):
                total_pdf_count += 1
            elif file.filename.lower().endswith('.zip'):
                with zipfile.ZipFile(file, 'r') as ref_zip:
                    pdfs_in_zip = [z for z in ref_zip.infolist() if not z.is_dir() and z.filename.lower().endswith('.pdf')]
                    total_pdf_count += len(pdfs_in_zip)
        
        if total_pdf_count > MAX_PDF_LIMIT:
            return jsonify({"error": f"制限を超えています（合計{total_pdf_count}個）。20個以内にしてください。"}), 400

        # 2. 変換処理
        for file in files:
            filename_low = file.filename.lower()
            if filename_low.endswith('.zip'):
                file.seek(0)
                with zipfile.ZipFile(io.BytesIO(file.read()), 'r') as ref_zip:
                    for z_info in ref_zip.infolist():
                        if z_info.is_dir() or not z_info.filename.lower().endswith('.pdf'): continue
                        with ref_zip.open(z_info) as z_file:
                            tmp_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.pdf")
                            with open(tmp_path, "wb") as f: f.write(z_file.read())
                            images = process_pdf_to_images(tmp_path, selected_dpi, is_transparent)
                            base_path = os.path.splitext(z_info.filename)[0]
                            for suffix, data in images: all_converted_data.append((base_path + suffix, data))
                            if os.path.exists(tmp_path): os.remove(tmp_path)
            elif filename_low.endswith('.pdf'):
                tmp_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.pdf")
                file.save(tmp_path)
                images = process_pdf_to_images(tmp_path, selected_dpi, is_transparent)
                base_path = os.path.splitext(file.filename)[0]
                for suffix, data in images: all_converted_data.append((base_path + suffix, data))
                if os.path.exists(tmp_path): os.remove(tmp_path)

        if not all_converted_data:
            return jsonify({"error": "変換可能なPDFが見つかりませんでした"}), 400

        # 3. 出力
        zip_output = io.BytesIO()
        if len(all_converted_data) == 1:
            # 1つの場合は直接返したいが、Ajax通信のためバイナリをそのまま送る
            path, data = all_converted_data[0]
            return send_file(io.BytesIO(data), mimetype='image/png', as_attachment=True, download_name=os.path.basename(path))

        with zipfile.ZipFile(zip_output, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for path, data in all_converted_data:
                zip_file.writestr(path, data)
        zip_output.seek(0)
        return send_file(zip_output, mimetype='application/zip', as_attachment=True, download_name="converted_assets.zip")

    except Exception as e:
        return jsonify({"error": f"サーバーエラーが発生しました: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
