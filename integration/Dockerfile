FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py dcr_integration.py preparedness_state.py ./

CMD ["python", "app.py"]
