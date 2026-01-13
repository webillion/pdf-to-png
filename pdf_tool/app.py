import os, uuid, zipfile, io, gc, time, traceback
from flask import Flask, request, render_template, send_file, jsonify
from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image, ImageChops

app = Flask(__name__)
# Renderの一時領域（必ず/tmpを使用）
UPLOAD_FOLDER = '/tmp'

def force_cleanup():
    """メモリをOSへ即座に返却し、SIGKILLを回避する"""
    gc.collect()
    time.sleep(0.1)

def make_transparent_perfect(image):
    """
    ピクセルループを一切使わず、ベクトル演算で透過。
    300DPIの大容量データでもメモリをほぼ使いません。
    """
    img = image.convert("RGBA")
    r, g, b, a = img.split()
    
    # 明るさ245以上の白をマスク化（C言語レベルの高速処理）
    mask = r.point(lambda x: 255 if x > 245 else 0)
    mask = ImageChops.multiply(mask, g.point(lambda x: 255 if x > 245 else 0))
    mask = ImageChops.multiply(mask, b.point(lambda x: 255 if x > 245 else 0))
    
    # マスクを反転させてアルファチャンネルに適用
    inv_mask = ImageChops.invert(mask)
    new_a = ImageChops.multiply(a, inv_mask)
    img.putalpha(new_a)
    
    # 処理済みオブジェクトの削除
    del r, g, b, a, mask, inv_mask, new_a
    return img

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    force_cleanup()
    
    # パスワード（将来の収益化用）
    pwd = request.form.get('password', '')
    is_pro = (pwd in ["admin1234", "pro_user_77"])
    
    files = request.files.getlist('file')
    dpi = int(request.form.get('dpi', 150))
    is_transparent = 'transparent' in request.form
    
    zip_buffer = io.BytesIO()
    total_count = 0
    
    try:
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as master_zip:
            for f in files:
                if f.filename == '': continue
                
                # xref table エラーを防ぐため一時ファイルを完全に書き出す
                ext = os.path.splitext(f.filename)[1]
                tmp_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}{ext}")
                f.save(tmp_path)
                
                try:
                    # ページ数を取得
                    info = pdfinfo_from_path(tmp_path)
                    total_pages = info["Pages"]
                    base_name = os.path.splitext(f.filename)[0]
                    
                    for p in range(1, total_pages + 1):
                        # 1ページずつCairoエンジンで処理。これが「落ちない」ための最重要ポイント。
                        pages = convert_from_path(
                            tmp_path, dpi=dpi, first_page=p, last_page=p,
                            use_pdftocairo=True, thread_count=1
                        )
                        if not pages: continue
                        
                        img = pages[0]
                        if is_transparent:
                            img = make_transparent_perfect(img)
                        
                        # PNGとしてZIPへ格納
                        img_io = io.BytesIO()
                        img.save(img_io, format='PNG', optimize=False)
                        master_zip.writestr(f"{base_name}_{p:03d}.png", img_io.getvalue())
                        
                        # ページごとにメモリをリセット
                        img.close()
                        img_io.close()
                        del img, pages
                        force_cleanup()
                        total_count += 1
                        
                finally:
                    # 処理後（またはエラー時）にファイルを確実に削除
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
        
        if total_count == 0:
            return jsonify({"error": "変換できるページがありませんでした。"}), 500

        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name="materials.zip")

    except Exception as e:
        print(f"ERROR: {traceback.format_exc()}")
        return jsonify({"error": f"処理失敗: {str(e)}"}), 500
    finally:
        force_cleanup()

if __name__ == '__main__':
    # Renderの環境変数に合わせて起動
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
