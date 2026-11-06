FROM python:3.11-slim

WORKDIR /app

COPY --from=dcr-sdk . /opt/dcr-sdk
COPY requirements.txt .
RUN pip install --no-cache-dir /opt/dcr-sdk -r requirements.txt

COPY . .

CMD ["python", "-u", "app.py"]
