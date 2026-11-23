import asyncio
import os
import threading

import grpc
from flask import Flask, jsonify, request
from pyzeebe import Job, ZeebeClient, ZeebeWorker

ZEEBE_ADDRESS = os.getenv("ZEEBE_ADDRESS", "zeebe:26500")
BPMN_FILE = os.getenv(
    "BPMN_FILE", "/bpmn/Disaster_Attention_Protocol_camunda.bpmn"
)
FORECAST_PROCESS_ID = os.getenv("FORECAST_PROCESS_ID", "Process_0q7dfku")

app = Flask(__name__)
client: ZeebeClient | None = None
worker: ZeebeWorker | None = None
event_loop: asyncio.AbstractEventLoop | None = None


def run_async(coroutine):
    if event_loop is None:
        raise RuntimeError("Camunda service is not ready")
    future = asyncio.run_coroutine_threadsafe(coroutine, event_loop)
    return future.result(timeout=30)


@app.get("/health")
def health():
    if client is None or worker is None:
        return jsonify({"status": "starting"}), 503
    return jsonify({"status": "ok"})


@app.post("/forecast_warning")
def forecast_warning():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "JSON data is required"}), 400

    try:
        water_level = float(data["waterLevel"])
        critical_level = float(data["criticalLevel"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Valid waterLevel and criticalLevel are required"}), 400

    if client is None or worker is None:
        return jsonify({"error": "Camunda is not ready"}), 503

    process_key = run_async(
        client.run_process(
            FORECAST_PROCESS_ID,
            variables={
                "waterLevel": water_level,
                "criticalLevel": critical_level,
                "location": data.get("location", ""),
            },
        )
    )
    return jsonify({"status": "started", "case_id": str(process_key)}), 202


async def evaluate_forecast_task(waterLevel, criticalLevel):
    return {"isCritical": float(waterLevel) >= float(criticalLevel)}


async def send_preparedness_notice_task(job: Job):
    print(
        f"[Camunda] Simulating preparedness notice for {job.process_instance_key}",
        flush=True,
    )
    return {"preparednessNoticeSimulated": True}


async def deploy_and_work():
    global client, worker

    for attempt in range(1, 31):
        channel = grpc.aio.insecure_channel(ZEEBE_ADDRESS)
        candidate_client = ZeebeClient(grpc_channel=channel)
        try:
            await candidate_client.deploy_process(BPMN_FILE)
            print(f"[Camunda] BPMN deployed: {BPMN_FILE}", flush=True)
            client = candidate_client
            break
        except Exception as error:
            print(
                f"[Camunda] deployment attempt {attempt} failed: {error!r}",
                flush=True,
            )
            await channel.close()
            if attempt == 30:
                raise
            await asyncio.sleep(2)

    worker = ZeebeWorker(grpc_channel=channel)
    worker.task(
        task_type="evaluate-forecast",
        variables_to_fetch=["waterLevel", "criticalLevel"],
    )(evaluate_forecast_task)
    worker.task(task_type="send-preparedness-notice")(
        send_preparedness_notice_task
    )
    await worker.work()


def serve_http():
    app.run(host="0.0.0.0", port=5001, threaded=True)


async def main():
    global event_loop
    event_loop = asyncio.get_running_loop()
    threading.Thread(target=serve_http, daemon=True).start()
    await deploy_and_work()


if __name__ == "__main__":
    asyncio.run(main())
