FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY constants ./constants
COPY dmi ./dmi
COPY models ./models
COPY service ./service
COPY ingestion_server.py .

CMD ["uvicorn", "ingestion_server:app", "--host", "0.0.0.0", "--port", "5000"]
