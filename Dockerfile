# 1. Pythonが入っている小さなコンピューターを用意
FROM python:3.9-slim

# 2. PDF変換に必要なソフト（Poppler）をインストール
RUN apt-get update && apt-get install -y poppler-utils

# 3. 自分のプログラムをその中に入れる
WORKDIR /app
COPY . /app

# 4. 必要なライブラリ（Flaskなど）をインストール
RUN pip install --no-cache-dir -r requirements.txt

# 5. サイトを起動する
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "app:app"]