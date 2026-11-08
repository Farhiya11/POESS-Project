import os

import requests
from flask import Flask, jsonify, request


INTEGRATION_URL = os.getenv("INTEGRATION_URL", "http://communication:5001")

app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
