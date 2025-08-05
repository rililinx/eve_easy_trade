FROM python:3.11-slim

WORKDIR /app
COPY . .

# Install required dependencies
RUN pip install --no-cache-dir streamlit redis pandas

EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
