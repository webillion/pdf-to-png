FROM python:3.9-slim
RUN apt-get update && apt-get install -y poppler-utils
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "app:app"]
