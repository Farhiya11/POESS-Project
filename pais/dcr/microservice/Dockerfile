FROM python:3.11-slim

WORKDIR /app

COPY --from=dcr-sdk . /opt/dcr-sdk
COPY --from=dcr-engine . /opt/dcr-engine
COPY requirements.txt .
RUN pip install --no-cache-dir /opt/dcr-sdk /opt/dcr-engine -r requirements.txt

COPY . .

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5001"]
