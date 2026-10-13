# AutoTrading VN - ảnh Docker cho máy chủ Internet (Render, Railway, VPS…).
# Giao diện đã build sẵn trong frontend/dist (CI kiểm tra khớp mã nguồn) - không cần Node.js.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=ICT-7 \
    DB_PATH=backend/data/autotrading.sqlite3
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY frontend/dist frontend/dist
COPY manage.py .env.example ./
# Dữ liệu (tài khoản, danh mục, lệnh…) nằm ở /app/backend/data → gắn ổ đĩa bền vững vào thư mục này
RUN mkdir -p backend/data
EXPOSE 8000
# Nhà cung cấp đặt biến PORT; chạy một tiến trình (bộ lập lịch Auto-Trader chạy trong tiến trình này)
CMD ["sh", "-c", "exec uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}"]
