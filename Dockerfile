# Giao diện đã build sẵn trong frontend/dist (CI kiểm tra khớp mã nguồn) - không cần Node.js
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY frontend/dist frontend/dist
COPY manage.py .env.example ./
ENV DB_PATH=backend/data/autotrading.sqlite3
VOLUME ["/app/backend/data"]
EXPOSE 8000
# Tạo quản trị viên đầu tiên: docker exec -it <container> python manage.py create-admin
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
