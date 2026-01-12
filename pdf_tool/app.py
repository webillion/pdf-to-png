import os, uuid, time, zipfile, io
from flask import Flask, request, render_template, send_file, make_response, jsonify
from pdf2image import convert_from_path

app = Flask(__name__)
# 50MBまでのアップロードを許可
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
UPLOAD_FOLDER = 'temp_storage'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def process_pdf_to_images(pdf_path, dpi, is_transparent):
    """PDFをPNG画像に変換（メモリ消費を抑える修正版）"""
    try:
        # メモリ節約のため thread_count=1 に設定
        pages = convert_from_path(pdf_path, dpi=dpi, thread_count=1)
        # 1ファイルあたり最大15ページ制限
        target_pages = pages[:15]
        
        output_images = []
        for i, page in enumerate(target_pages):
            if is_transparent:
                page = page.convert("RGBA")
                datas = page.getdata()
                new_data = [(255, 255, 255, 0) if d[0]>240 and d[1]>240 and d[2]>240 else d for d in datas]
                page.putdata(new_data)
            else:
                page = page.convert("RGB")
            
            img_io = io.BytesIO()
            page.save(img_io, format='PNG')
            output_images.append((f"_{i+1:03d}.png", img_io.getvalue()))
            
            # 各ページのオブジェクトを明示的に削除してメモリを空ける
            page.close()
            
        return output_images
    except Exception as e:
        print(f"Error processing {pdf_path}: {e}")
        return []

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    try:
        files = request.files.getlist('file')
        if not files or files[0].filename == '':
            return jsonify({"error": "ファイルが正しく読み込めませんでした。"}), 400

        selected_dpi = int(request.form.get('dpi', 150))
        is_transparent = 'transparent' in request.form
        
        all_converted_data = []
        total_pdf_count = 0
        MAX_PDF_LIMIT = 20

        for file in files:
            filename_low = file.filename.lower()
            
            if filename_low.endswith('.zip'):
                file.seek(0)
                file_content = file.read()
                with zipfile.ZipFile(io.BytesIO(file_content), 'r') as ref_zip:
                    pdf_infos = [z for z in ref_zip.infolist() if not z.is_dir() and z.filename.lower().endswith('.pdf')]
                    total_pdf_count += len(pdf_infos)
                    
                    if total_pdf_count > MAX_PDF_LIMIT:
                        return jsonify({"error": f"処理制限を超えています（合計{total_pdf_count}/20個）"}), 400

                    for z_info in pdf_infos:
                        with ref_zip.open(z_info) as z_file:
                            tmp_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.pdf")
                            with open(tmp_path, "wb") as f: f.write(z_file.read())
                            images = process_pdf_to_images(tmp_path, selected_dpi, is_transparent)
                            base_path = os.path.splitext(z_info.filename)[0]
                            for suffix, data in images:
                                all_converted_data.append((base_path + suffix, data))
                            if os.path.exists(tmp_path): os.remove(tmp_path)

            elif filename_low.endswith('.pdf'):
                total_pdf_count += 1
                if total_pdf_count > MAX_PDF_LIMIT:
                    return jsonify({"error": "合計20ファイルまでしか処理できません。"}), 400

                tmp_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.pdf")
                file.save(tmp_path)
                images = process_pdf_to_images(tmp_path, selected_dpi, is_transparent)
                base_path = os.path.splitext(file.filename)[0]
                for suffix, data in images:
                    all_converted_data.append((base_path + suffix, data))
                if os.path.exists(tmp_path): os.remove(tmp_path)

        if not all_converted_data:
            return jsonify({"error": "変換可能なPDFが見つかりませんでした。"}), 400

        zip_output = io.BytesIO()
        if len(all_converted_data) == 1:
            path, data = all_converted_data[0]
            return send_file(io.BytesIO(data), mimetype='image/png', as_attachment=True, download_name=os.path.basename(path))

        with zipfile.ZipFile(zip_output, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for path, data in all_converted_data:
                zip_file.writestr(path, data)
        
        zip_output.seek(0)
        return send_file(zip_output, mimetype='application/zip', as_attachment=True, download_name="materials_collection.zip")

    except Exception as e:
        return jsonify({"error": f"サーバーエラー: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
