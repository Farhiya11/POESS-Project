FROM python:3.11-slim

WORKDIR /app

COPY app.py /app/

RUN pip install flask tzdata

# Create the mounted event log root
RUN mkdir -p /data

CMD ["python", "app.py"]
