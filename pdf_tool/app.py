import os, uuid, zipfile, io, gc, time
from flask import Flask, request, render_template, send_file, jsonify
from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image, ImageChops

app = Flask(__name__)
UPLOAD_FOLDER = '/tmp'

def force_cleanup():
    gc.collect()
    time.sleep(0.1)

def make_transparent_standard(image):
    """
    以前成功していた「白を抜く」ロジックを、低メモリな演算方式で再現。
    """
    img = image.convert("RGBA")
    r, g, b, a = img.split()
    # 245以上の明るさを白と判定
    mask = r.point(lambda x: 255 if x > 245 else 0)
    mask = ImageChops.multiply(mask, g.point(lambda x: 255 if x > 245 else 0))
    mask = ImageChops.multiply(mask, b.point(lambda x: 255 if x > 245 else 0))
    inv_mask = ImageChops.invert(mask)
    new_a = ImageChops.multiply(a, inv_mask)
    img.putalpha(new_a)
    return img

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    force_cleanup()
    files = request.files.getlist('file')
    dpi = int(request.form.get('dpi', 150))
    is_transparent = 'transparent' in request.form
    zip_buffer = io.BytesIO()
    
    try:
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as master_zip:
            for f in files:
                if f.filename == '': continue
                tmp_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.pdf")
                f.save(tmp_path)
                
                info = pdfinfo_from_path(tmp_path)
                for p in range(1, info["Pages"] + 1):
                    # 1ページずつCairoエンジンで処理
                    pages = convert_from_path(
                        tmp_path, dpi=dpi, first_page=p, last_page=p,
                        use_pdftocairo=True, thread_count=1
                    )
                    if not pages: continue
                    img = pages[0]
                    if is_transparent:
                        img = make_transparent_standard(img)
                    
                    img_io = io.BytesIO()
                    img.save(img_io, format='PNG')
                    master_zip.writestr(f"{os.path.splitext(f.name)[0]}_{p:03d}.png", img_io.getvalue())
                    img.close()
                    force_cleanup()
                
                if os.path.exists(tmp_path): os.remove(tmp_path)
        
        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name="output.zip")
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        force_cleanup()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
