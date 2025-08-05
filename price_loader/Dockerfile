FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir redis
EXPOSE 8000
CMD ["python", "price_loader.py"]
