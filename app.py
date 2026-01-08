import os
from flask import Flask, render_template, request
from pdf2image import convert_from_path

app = Flask(__name__)

# 保存先フォルダの設定
UPLOAD_FOLDER = 'static'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 【追加】起動時にstaticフォルダがなければ作成する
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/', methods=['GET', 'POST'])
def index():
    images = []
    if request.method == 'POST':
        # 1. 送られてきたファイルをチェック
        if 'file' not in request.files:
            return "ファイルがありません"
        
        pdf_file = request.files['file']
        
        if pdf_file.filename == '':
            return "ファイルが選択されていません"

        if pdf_file:
            # 2. ファイルを保存するパスを作成
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], "temp.pdf")
            
            # 【重要】保存前に念のためフォルダがあるか再確認
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            
            pdf_file.save(pdf_path)

            # 3. PDFを画像に変換
            # Windowsでエラーが出る場合は poppler_path=r'C:\path\to\bin' を追加
            try:
                pages = convert_from_path(pdf_path)
                
                # 4. 画像を保存してリストに登録
                for i, page in enumerate(pages):
                    img_name = f"result_{i}.png"
                    img_path = os.path.join(app.config['UPLOAD_FOLDER'], img_name)
                    page.save(img_path, "PNG")
                    images.append(img_name)
            except Exception as e:
                return f"変換中にエラーが発生しました: {e}"

    return render_template('index.html', images=images)

if __name__ == '__main__':
    app.run(debug=True)