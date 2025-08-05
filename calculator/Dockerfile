FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir redis
EXPOSE 8001
CMD ["python", "calculator.py"]
