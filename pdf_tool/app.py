import os, uuid, zipfile, io, gc
from flask import Flask, request, render_template, send_file, jsonify
from pdf2image import convert_from_path

app = Flask(__name__)
# 50MBまでのアップロードを許可
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
UPLOAD_FOLDER = 'temp_storage'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def process_pdf_to_zip(pdf_path, dpi, is_transparent, zip_file, base_filename):
    """PDFを解析し、1枚ずつZIPに書き込んでメモリから即消去する"""
    try:
        # thread_count=1 でメモリ爆発を防止
        pages = convert_from_path(pdf_path, dpi=dpi, thread_count=1)
        target_pages = pages[:15]
        
        for i, page in enumerate(target_pages):
            if is_transparent:
                page = page.convert("RGBA")
                datas = page.getdata()
                # 高速透過処理
                new_data = [(255, 255, 255, 0) if d[0]>240 and d[1]>240 and d[2]>240 else d for d in datas]
                page.putdata(new_data)
            else:
                page = page.convert("RGB")
            
            # 画像をバイナリ化して即ZIP書き込み
            img_io = io.BytesIO()
            page.save(img_io, format='PNG', optimize=False)
            zip_file.writestr(f"{base_filename}_{i+1:03d}.png", img_io.getvalue())
            
            # 使用済みオブジェクトの明示的削除とメモリ解放
            img_io.close()
            page.close()
            del page
            
        del pages
        gc.collect() # 1ファイルごとにゴミ拾い
        return True
    except Exception as e:
        print(f"Error processing {base_filename}: {e}")
        return False

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    try:
        files = request.files.getlist('file')
        if not files or files[0].filename == '':
            return jsonify({"error": "ファイルが選択されていません。"}), 400

        selected_dpi = int(request.form.get('dpi', 150))
        is_transparent = 'transparent' in request.form
        
        # メモリ上にZIPを作成
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as master_zip:
            total_pdf_count = 0
            
            for file in files:
                if total_pdf_count >= 20: break
                filename_low = file.filename.lower()
                
                # 単一PDFの処理
                if filename_low.endswith('.pdf'):
                    total_pdf_count += 1
                    tmp_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.pdf")
                    file.save(tmp_path)
                    
                    base_name = os.path.splitext(file.filename)[0]
                    process_pdf_to_zip(tmp_path, selected_dpi, is_transparent, master_zip, base_name)
                    
                    if os.path.exists(tmp_path): os.remove(tmp_path)

                # ZIPファイル（中身がPDF）の処理
                elif filename_low.endswith('.zip'):
                    file_content = file.read()
                    with zipfile.ZipFile(io.BytesIO(file_content), 'r') as ref_zip:
                        pdf_infos = [z for z in ref_zip.infolist() if not z.is_dir() and z.filename.lower().endswith('.pdf')]
                        for z_info in pdf_infos:
                            if total_pdf_count >= 20: break
                            total_pdf_count += 1
                            with ref_zip.open(z_info) as z_file:
                                tmp_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.pdf")
                                with open(tmp_path, "wb") as f: f.write(z_file.read())
                                base_name = os.path.splitext(z_info.filename)[0]
                                process_pdf_to_zip(tmp_path, selected_dpi, is_transparent, master_zip, base_name)
                                if os.path.exists(tmp_path): os.remove(tmp_path)

        zip_buffer.seek(0)
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name="material_studio_output.zip"
        )

    except Exception as e:
        return jsonify({"error": f"サーバー負荷エラー: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
