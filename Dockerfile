FROM python:3.10-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV COOKIE_SECURE=true
CMD ["sh", "-c", "uvicorn edumind.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
