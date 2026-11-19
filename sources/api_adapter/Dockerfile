FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .
COPY models ./models
COPY tests/mock_data ./tests/mock_data

CMD ["python", "app.py"]
