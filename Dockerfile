FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV SII_ADMIN_TOKEN=change-me
EXPOSE 8000
CMD ["uvicorn","sii.app:app","--host","0.0.0.0","--port","8000"]
