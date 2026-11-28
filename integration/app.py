import asyncio
import json
import math
import os
import threading
from dataclasses import replace
from datetime import datetime, timezone

import grpc
import requests
from flask import Flask, jsonify, request
from pyzeebe import Job, ZeebeClient, ZeebeWorker

from dcr_integration import dcr_bp
from preparedness_episode_store import PreparednessEpisodeStore
from preparedness_state import (
    DMI_WARNING_CATEGORIES,
    PREPAREDNESS_LEVEL_RANK,
    AlertLevel,
    PreparednessWarningDecision,
)

ZEEBE_ADDRESS = os.getenv("ZEEBE_ADDRESS", "zeebe:26500")
BPMN_FILE = os.getenv("BPMN_FILE", "/bpmn/food_order.bpmn")
PREPAREDNESS_WARNING_BPMN_FILE = os.getenv(
    "PREPAREDNESS_WARNING_BPMN_FILE",
    "/bpmn/Disaster_Attention_Protocol_camunda.bpmn",
)
SIDDHI_CALLBACK_URL = os.getenv("SIDDHI_CALLBACK_URL", "http://siddhi:7072/middleman")
CUSTOMER_PROCESS_ID = "Process_06p6nly"
PREPAREDNESS_WARNING_PROCESS_ID = os.getenv(
    "PREPAREDNESS_WARNING_PROCESS_ID",
    "Process_0q7dfku",
)
PREPAREDNESS_PROCESS_NAME = "Storm Surge Preparedness"
PREPAREDNESS_LOG_TIMEOUT_SECONDS = 2

app = Flask(__name__)
app.register_blueprint(dcr_bp)
client = None
worker = None
event_loop = None
process_keys = {}
preparedness_episode_store = PreparednessEpisodeStore()
alert_process_start_lock = threading.RLock()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_order_id(data):
    return data.get("order_id") or data.get("event", {}).get("order_id")


def callback(order_id, case_id, event, payload=None, error=""):
    body = {
        "order_id": order_id,
        "case_id": str(case_id),
        "event": event,
        "process_engine": "BPMN",
        "timestamp": now_iso(),
        "role": "camunda",
        "payload": json.dumps(payload or {}),
        "error": error,
    }
    response = requests.post(SIDDHI_CALLBACK_URL, json=body, timeout=30)
    response.raise_for_status()


def preparedness_refresh_case_id(refresh_id):
    return f"preparedness-refresh-{refresh_id or 'unknown'}"


def preparedness_case_id_for_refresh(location_id, refresh_id):
    if isinstance(location_id, str) and location_id.strip():
        active_case_id = preparedness_episode_store.case_id_for(location_id)
        if active_case_id is not None:
            return active_case_id
    return preparedness_refresh_case_id(refresh_id)


def emit_preparedness_event(
    event,
    case_id,
    refresh_id,
    location_id,
    payload,
    *,
    role="communication",
    error="",
):
    """Send an audit event through Siddhi without blocking process handling."""
    try:
        event_payload = {
            "process_name": PREPAREDNESS_PROCESS_NAME,
            "refresh_id": refresh_id,
            "location_id": location_id,
            **payload,
        }
        body = {
            "order_id": refresh_id or "",
            "case_id": case_id or preparedness_refresh_case_id(refresh_id),
            "event": event,
            "process_engine": "BPMN",
            "timestamp": now_iso(),
            "role": role,
            "payload": json.dumps(event_payload, separators=(",", ":")),
            "error": error,
        }
        response = requests.post(
            SIDDHI_CALLBACK_URL,
            json=body,
            timeout=PREPAREDNESS_LOG_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except (requests.RequestException, TypeError, ValueError):
        app.logger.exception(
            "Unable to log preparedness event %s for refresh %s",
            event,
            refresh_id,
        )


def get_case_id(order_id, supplied_case_id=None):
    return supplied_case_id or process_keys.get(order_id, "UNKNOWN_CASE")


def run_async(coroutine):
    if event_loop is None:
        raise RuntimeError("Communication adapter is not ready")
    future = asyncio.run_coroutine_threadsafe(coroutine, event_loop)
    return future.result(timeout=30)


async def publish_message(name, order_id, variables):
    await client.publish_message(name, str(order_id), variables)


def start_preparedness_warning_process(
    case_id: str, refresh_id: str, decision: PreparednessWarningDecision
) -> str:
    with alert_process_start_lock:
        if client is None or worker is None:
            raise RuntimeError("Communication adapter is not ready")
        process_instance_key = preparedness_episode_store.process_instance_for(case_id)
        if process_instance_key is not None:
            return process_instance_key

        variables = decision_variables(case_id, refresh_id, decision)
        variables["operationalPreparednessCompleted"] = False
        process_instance_key = run_async(
            client.run_process(
                PREPAREDNESS_WARNING_PROCESS_ID,
                variables=variables,
            )
        )
        process_instance_key = str(process_instance_key)
        preparedness_episode_store.record_process_instance(case_id, process_instance_key)
        app.logger.info(
            "Started preparedness warning process %s for case %s at location %s",
            process_instance_key,
            case_id,
            decision.location_id,
        )
        return process_instance_key


def decision_variables(
    case_id: str, refresh_id: str, decision: PreparednessWarningDecision
) -> dict[str, object]:
    return {
        "alertLevel": decision.alert_level.value,
        "caseId": case_id,
        "criticalLevel": decision.critical_level_cm,
        "decisionReason": decision.reason,
        "dmiWarningCategory": decision.dmi_warning_category,
        "categoryTimeToCriticalHours": decision.category_time_to_critical_hours,
        "categoryForecastValueCm": decision.category_forecast_value_cm,
        "forecastValueCm": decision.forecast_value_cm,
        "locationId": decision.location_id,
        "refreshId": refresh_id,
        "timeToCriticalHours": decision.time_to_critical_hours,
        "waterLevel": decision.forecast_value_cm,
    }


def publish_alert_level(
    case_id: str, refresh_id: str, decision: PreparednessWarningDecision
) -> None:
    run_async(
        publish_message(
            "AlertLevelUpdated",
            case_id,
            decision_variables(case_id, refresh_id, decision),
        )
    )


def handle_preparedness_decision(decision, refresh_id, raw_payload=None):
    with alert_process_start_lock:
        location_id = decision.location_id
        audit_payload = raw_payload if isinstance(raw_payload, dict) else {}
        if preparedness_episode_store.has_processed_refresh(
            location_id, refresh_id
        ):
            duplicate_case_id = preparedness_episode_store.case_id_for(
                location_id
            ) or preparedness_refresh_case_id(refresh_id)
            emit_preparedness_event(
                "PreparednessRefreshDuplicate",
                duplicate_case_id,
                refresh_id,
                location_id,
                {"event_type": "duplicate", "decision": audit_payload},
            )
            return jsonify(
                {
                    "status": "duplicate",
                    "location_id": location_id,
                    "refresh_id": refresh_id,
                }
            ), 200

        previous_case_id = preparedness_episode_store.case_id_for(location_id)
        if decision.alert_level is AlertLevel.NONE:
            previous_alert_level = (
                preparedness_episode_store.alert_level_for(previous_case_id)
                if previous_case_id is not None
                else None
            )
            event_case_id = previous_case_id or preparedness_refresh_case_id(
                refresh_id
            )
            emit_preparedness_event(
                "PreparednessRefreshEvaluated",
                event_case_id,
                refresh_id,
                location_id,
                {
                    "event_type": "evaluated",
                    "status": "decision",
                    "transition": "clear" if previous_case_id else "none",
                    "decision": audit_payload,
                },
            )
            if previous_case_id is not None:
                process_instance_key = preparedness_episode_store.process_instance_for(
                    previous_case_id
                )
                if process_instance_key is not None:
                    try:
                        publish_alert_level(
                            previous_case_id, refresh_id, decision
                        )
                    except (grpc.RpcError, RuntimeError, TimeoutError):
                        app.logger.exception(
                            "Unable to clear preparedness warning process for case %s",
                            previous_case_id,
                        )
                        return jsonify(
                            {
                                "error": "Alert-clear update could not be delivered",
                                "case_id": previous_case_id,
                                "refresh_id": refresh_id,
                            }
                        ), 503
            try:
                preparedness_episode_store.update_episode(location_id, False)
                preparedness_episode_store.record_processed_refresh(
                    location_id, refresh_id
                )
            except RuntimeError:
                app.logger.exception("Unable to persist cleared preparedness state")
                return jsonify({"error": "Alert state is unavailable"}), 503
            if previous_case_id is not None:
                emit_preparedness_event(
                    "PreparednessEpisodeCleared",
                    previous_case_id,
                    refresh_id,
                    location_id,
                    {
                        "event_type": "episode_cleared",
                        "previous_alert_level": previous_alert_level.value
                        if previous_alert_level is not None
                        else None,
                        "decision": audit_payload,
                    },
                )
            return jsonify(
                {
                    "status": "clear",
                    "transition": (
                        "cleared" if previous_case_id is not None else "none"
                    ),
                    "alert_level": AlertLevel.NONE.value,
                    "dmi_warning_category": decision.dmi_warning_category,
                    "case_id": previous_case_id,
                    "refresh_id": refresh_id,
                    "time_to_critical_hours": None,
                    "forecast_value_cm": None,
                    "reason": decision.reason,
                }
            ), 200

        try:
            case_id = preparedness_episode_store.update_episode(location_id, True)
            if case_id is None:
                raise RuntimeError("Unable to create alert episode")
            emit_preparedness_event(
                "PreparednessRefreshEvaluated",
                case_id,
                refresh_id,
                location_id,
                {
                    "event_type": "evaluated",
                    "status": "decision",
                    "decision": audit_payload,
                },
            )
            previous_level = preparedness_episode_store.alert_level_for(case_id)
            previous_category = preparedness_episode_store.dmi_warning_category_for(
                case_id
            )
            alert_level = decision.alert_level
            if (
                previous_level is not None
                and PREPAREDNESS_LEVEL_RANK[previous_level]
                > PREPAREDNESS_LEVEL_RANK[alert_level]
            ):
                alert_level = previous_level
                decision = replace(
                    decision,
                    alert_level=alert_level,
                    reason="previous_preparedness_level_retained_until_clear",
                )
            process_instance_key = preparedness_episode_store.process_instance_for(
                case_id
            )
            if process_instance_key is None:
                process_instance_key = start_preparedness_warning_process(
                    case_id=case_id,
                    refresh_id=refresh_id,
                    decision=decision,
                )
                preparedness_episode_store.record_process_instance(
                    case_id, process_instance_key
                )
                preparedness_episode_store.record_alert_level(case_id, alert_level)
                if decision.dmi_warning_category != "NONE":
                    preparedness_episode_store.record_dmi_warning_category(
                        case_id, decision.dmi_warning_category
                    )
            elif (
                previous_level is None
                or alert_level is not previous_level
                or decision.dmi_warning_category != previous_category
            ):
                publish_alert_level(case_id, refresh_id, decision)
                preparedness_episode_store.record_alert_level(case_id, alert_level)
                if decision.dmi_warning_category != "NONE":
                    preparedness_episode_store.record_dmi_warning_category(
                        case_id, decision.dmi_warning_category
                    )
            elif decision.dmi_warning_category != "NONE":
                preparedness_episode_store.record_dmi_warning_category(
                    case_id, decision.dmi_warning_category
                )
            preparedness_episode_store.record_processed_refresh(
                location_id, refresh_id
            )
        except RuntimeError:
            app.logger.exception(
                "Unable to update preparedness warning state or process"
            )
            return jsonify({"error": "Alert state or process is unavailable"}), 503
        except (grpc.RpcError, TimeoutError):
            app.logger.exception(
                "Unable to update preparedness warning process for case %s", case_id
            )
            return jsonify(
                {
                    "error": "Preparedness-level update could not be delivered",
                    "case_id": case_id,
                    "refresh_id": refresh_id,
                }
            ), 503

        transition = "opened" if previous_case_id is None else (
            "escalated"
            if previous_level is None
            or PREPAREDNESS_LEVEL_RANK[alert_level]
            > PREPAREDNESS_LEVEL_RANK[previous_level]
            else "continued"
        )
        emit_preparedness_event(
            {
                "opened": "PreparednessEpisodeOpened",
                "escalated": "PreparednessEpisodeEscalated",
                "continued": "PreparednessEpisodeContinued",
            }[transition],
            case_id,
            refresh_id,
            location_id,
            {
                "event_type": "episode_transition",
                "transition": transition,
                "previous_alert_level": previous_level.value
                if previous_level is not None
                else None,
                "previous_dmi_warning_category": previous_category,
                "alert_level": alert_level.value,
                "dmi_warning_category": decision.dmi_warning_category,
                "process_instance_key": process_instance_key,
                "decision": audit_payload,
            },
        )
        return jsonify(
            {
                "status": "warning",
                "transition": transition,
                "alert_level": decision.alert_level.value,
                "dmi_warning_category": decision.dmi_warning_category,
                "case_id": case_id,
                "process_instance_key": process_instance_key,
                "refresh_id": refresh_id,
                "time_to_critical_hours": decision.time_to_critical_hours,
                "forecast_value_cm": decision.forecast_value_cm,
                "critical_level_cm": decision.critical_level_cm,
                "reason": decision.reason,
            }
        ), 200


@app.get("/health")
def health():
    if client is None or worker is None:
        return jsonify({"status": "starting"}), 503
    return jsonify({"status": "ok"})


@app.post("/preparedness_decision")
def preparedness_decision():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "JSON data is required"}), 400

    event = data.get("event", data)
    if not isinstance(event, dict):
        return jsonify({"error": "event must be a JSON object"}), 400

    decision_json = event.get("decision_json")
    if not isinstance(decision_json, str):
        return jsonify({"error": "decision_json is required"}), 400
    try:
        payload = json.loads(decision_json)
    except json.JSONDecodeError:
        app.logger.error("Siddhi sent malformed decision JSON")
        return jsonify({"error": "decision_json must contain valid JSON"}), 400
    if not isinstance(payload, dict):
        return jsonify({"error": "decision_json must contain an object"}), 400

    status = payload.get("status")
    if status == "disabled":
        emit_preparedness_event(
            "PreparednessRefreshDisabled",
            preparedness_case_id_for_refresh(
                payload.get("location_id"), payload.get("refresh_id")
            ),
            payload.get("refresh_id"),
            payload.get("location_id"),
            {"event_type": "disabled", "decision": payload},
        )
        return jsonify(
            {
                "status": "disabled",
                "refresh_id": payload.get("refresh_id"),
            }
        ), 200
    if status in ("configuration_error", "input_error"):
        emit_preparedness_event(
            "PreparednessRefreshRejected",
            preparedness_case_id_for_refresh(
                payload.get("location_id"), payload.get("refresh_id")
            ),
            payload.get("refresh_id"),
            payload.get("location_id"),
            {
                "event_type": status,
                "decision": payload,
            },
            error=str(payload.get("reason") or status),
        )
        app.logger.error(
            "Siddhi rejected preparedness refresh %s: %s",
            payload.get("refresh_id"),
            payload.get("reason"),
        )
        return jsonify(
            {
                "error": "Siddhi could not evaluate the preparedness refresh",
                "reason": payload.get("reason"),
            }
        ), 503 if status == "configuration_error" else 400
    if status != "decision":
        emit_preparedness_event(
            "PreparednessRefreshRejected",
            preparedness_case_id_for_refresh(
                payload.get("location_id"), payload.get("refresh_id")
            ),
            payload.get("refresh_id"),
            payload.get("location_id"),
            {"event_type": "unsupported_status", "decision": payload},
            error="unsupported Siddhi decision status",
        )
        return jsonify({"error": "unsupported Siddhi decision status"}), 400

    def reject_decision(reason):
        emit_preparedness_event(
            "PreparednessRefreshRejected",
            preparedness_case_id_for_refresh(
                payload.get("location_id"), payload.get("refresh_id")
            ),
            payload.get("refresh_id"),
            payload.get("location_id"),
            {
                "event_type": "communication_validation_error",
                "decision": payload,
            },
            error=reason,
        )
        return jsonify({"error": reason}), 400

    location_id = payload.get("location_id")
    refresh_id = payload.get("refresh_id")
    reason = payload.get("reason")
    if not all(
        isinstance(value, str) and value.strip()
        for value in (location_id, refresh_id, reason)
    ):
        return reject_decision("location_id, refresh_id, and reason are required")

    try:
        alert_level = AlertLevel(payload.get("alert_level"))
    except (TypeError, ValueError):
        return reject_decision("alert_level is invalid")
    dmi_warning_category = payload.get("dmi_warning_category")
    if (
        not isinstance(dmi_warning_category, str)
        or dmi_warning_category not in DMI_WARNING_CATEGORIES
    ):
        return reject_decision("dmi_warning_category is invalid")

    optional_values = {}
    for field in (
        "time_to_critical_hours",
        "forecast_value_cm",
        "critical_level_cm",
        "category_time_to_critical_hours",
        "category_forecast_value_cm",
    ):
        value = payload.get(field)
        if value is None:
            optional_values[field] = None
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return reject_decision(f"{field} must be a finite number or null")
        try:
            finite_value = float(value)
        except OverflowError:
            return reject_decision(f"{field} must be a finite number or null")
        if not math.isfinite(finite_value):
            return reject_decision(f"{field} must be a finite number or null")
        optional_values[field] = finite_value
    if optional_values["critical_level_cm"] is None:
        return reject_decision("critical_level_cm is required for a decision")
    if alert_level is AlertLevel.NONE:
        if (
            optional_values["time_to_critical_hours"] is not None
            or optional_values["forecast_value_cm"] is not None
            or dmi_warning_category != "NONE"
        ):
            return reject_decision("NONE decisions cannot contain warning evidence")
    else:
        if (
            optional_values["time_to_critical_hours"] is None
            or optional_values["forecast_value_cm"] is None
        ):
            return reject_decision(
                "preparedness decisions require forecast evidence"
            )
        if (
            dmi_warning_category == "NONE"
            or optional_values["category_time_to_critical_hours"] is None
            or optional_values["category_forecast_value_cm"] is None
        ):
            return reject_decision(
                "active warning decisions require DMI category evidence"
            )

    decision = PreparednessWarningDecision(
        location_id=location_id.strip(),
        alert_level=alert_level,
        time_to_critical_hours=optional_values["time_to_critical_hours"],
        forecast_value_cm=optional_values["forecast_value_cm"],
        critical_level_cm=optional_values["critical_level_cm"],
        dmi_warning_category=dmi_warning_category,
        category_time_to_critical_hours=optional_values[
            "category_time_to_critical_hours"
        ],
        category_forecast_value_cm=optional_values["category_forecast_value_cm"],
        reason=reason,
    )
    return handle_preparedness_decision(
        decision,
        refresh_id.strip(),
        raw_payload=payload,
    )


@app.post("/place_order")
def place_order():
    data = request.get_json(force=True)
    order_id = get_order_id(data)
    if not order_id:
        return jsonify({"error": "order_id is required"}), 400

    process_key = run_async(client.run_process(
        CUSTOMER_PROCESS_ID,
        variables={"orderId": order_id},
    ))
    process_keys[order_id] = process_key
    callback(order_id, process_key, "PlaceOrder", {"processInstanceKey": process_key})
    return jsonify({"status": "accepted", "case_id": str(process_key)})


@app.post("/cancel_order")
def cancel_order():
    data = request.get_json(force=True)
    order_id = get_order_id(data)
    if not order_id:
        return jsonify({"error": "order_id is required"}), 400
    case_id = get_case_id(order_id, data.get("case_id"))
    run_async(publish_message("OrderCancelled", order_id, {"orderId": order_id, "caseId": case_id}))
    return jsonify({"status": "accepted"})


@app.post("/receive_order")
def receive_order():
    data = request.get_json(force=True)
    order_id = get_order_id(data)
    if not order_id:
        return jsonify({"error": "order_id is required"}), 400
    case_id = get_case_id(order_id, data.get("case_id"))
    run_async(publish_message("FoodReceived", order_id, {"orderId": order_id, "caseId": case_id}))
    return jsonify({"status": "accepted"})


@app.post("/pay_order")
def pay_order():
    data = request.get_json(force=True)
    order_id = get_order_id(data)
    if not order_id:
        return jsonify({"error": "order_id is required"}), 400
    return jsonify({"status": "accepted"})


async def place_order_task(orderId, job: Job):
    variables = {"orderId": orderId, "caseId": job.process_instance_key}
    order_id = orderId
    await publish_message("OrderCreated", order_id, variables)
    return variables


async def make_order_task(orderId, caseId=None, job: Job = None):
    return {"orderId": orderId, "caseId": caseId} if caseId else {"orderId": orderId}


async def cancel_order_task(orderId, caseId, job: Job):
    variables = {"orderId": orderId, "caseId": caseId}
    callback(orderId, caseId, "CancelOrder", variables)
    return variables


async def send_food_task(orderId, caseId=None, job: Job = None):
    variables = {"orderId": orderId, "caseId": caseId} if caseId else {"orderId": orderId}
    await publish_message("FoodReceived", orderId, variables)
    callback(orderId, caseId, "ReceiveOrder", variables)
    return variables


async def request_payment_task(orderId, caseId=None, job: Job = None):
    variables = {"orderId": orderId, "caseId": caseId} if caseId else {"orderId": orderId}
    callback(orderId, caseId, "PayOrder", variables)
    return variables


async def evaluate_forecast_task(alertLevel):
    try:
        parsed_level = AlertLevel(alertLevel)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Unknown preparedness alert level: {alertLevel!r}") from error
    return {"isCritical": parsed_level is not AlertLevel.NONE}


async def perform_preparedness_task(
    task_name, activity_name, caseId, alertLevel, refreshId=None, locationId=None
):
    try:
        print(
            f"[Camunda] Simulating {task_name} for case {caseId} "
            f"at alert level {alertLevel}",
            flush=True,
        )
        result = {f"{task_name}Completed": True}
    except Exception as error:
        emit_preparedness_event(
            activity_name,
            caseId,
            refreshId,
            locationId,
            {
                "event_type": "preparedness_task_failed",
                "lifecycle": "failed",
                "task_type": task_name,
                "alert_level": alertLevel,
            },
            role="camunda",
            error=str(error),
        )
        raise

    emit_preparedness_event(
        activity_name,
        caseId,
        refreshId,
        locationId,
        {
            "event_type": "preparedness_task_completed",
            "lifecycle": "complete",
            "task_type": task_name,
            "alert_level": alertLevel,
        },
        role="camunda",
    )
    return result


async def internal_preparedness_task(
    caseId, alertLevel, refreshId=None, locationId=None
):
    return await perform_preparedness_task(
        "internalPreparedness",
        "Internal preparedness",
        caseId,
        alertLevel,
        refreshId,
        locationId,
    )


async def information_preparedness_task(
    caseId, alertLevel, refreshId=None, locationId=None
):
    return await perform_preparedness_task(
        "informationPreparedness",
        "Information preparedness",
        caseId,
        alertLevel,
        refreshId,
        locationId,
    )


async def staff_preparedness_task(caseId, alertLevel, refreshId=None, locationId=None):
    return await perform_preparedness_task(
        "staffPreparedness",
        "Staff preparedness",
        caseId,
        alertLevel,
        refreshId,
        locationId,
    )


async def send_preparedness_notice_task(
    caseId, alertLevel, refreshId=None, locationId=None
):
    return await perform_preparedness_task(
        "operationalPreparedness",
        "Operational preparedness",
        caseId,
        alertLevel,
        refreshId,
        locationId,
    )


async def deploy_and_work():
    global client, worker
    for attempt in range(1, 31):
        channel = grpc.aio.insecure_channel(ZEEBE_ADDRESS)
        candidate_client = ZeebeClient(grpc_channel=channel)
        try:
            deployment = await candidate_client.deploy_process(BPMN_FILE)
            print(f"[Camunda] BPMN deployed: {deployment}", flush=True)
            alert_deployment = await candidate_client.deploy_process(
                PREPAREDNESS_WARNING_BPMN_FILE
            )
            print(f"[Camunda] Preparedness warning BPMN deployed: {alert_deployment}", flush=True)
            client = candidate_client
            break
        except Exception as error:
            cause = getattr(error, "__cause__", None)
            print(
                f"[Camunda] deployment attempt {attempt} failed: "
                f"{error!r}; cause={cause!r}",
                flush=True,
            )
            await channel.close()
            if attempt == 30:
                raise
            await asyncio.sleep(2)

    worker = ZeebeWorker(grpc_channel=channel)
    worker.task(task_type="place-order", variables_to_fetch=["orderId"])(place_order_task)
    worker.task(task_type="make-order", variables_to_fetch=["orderId", "caseId"])(make_order_task)
    worker.task(task_type="cancel-order", variables_to_fetch=["orderId", "caseId"])(cancel_order_task)
    worker.task(task_type="send-food", variables_to_fetch=["orderId", "caseId"])(send_food_task)
    worker.task(task_type="request-payment", variables_to_fetch=["orderId", "caseId"])(request_payment_task)
    worker.task(
        task_type="evaluate-forecast", variables_to_fetch=["alertLevel"]
    )(evaluate_forecast_task)
    worker.task(
        task_type="prepare-internal",
        variables_to_fetch=["caseId", "alertLevel", "refreshId", "locationId"],
    )(internal_preparedness_task)
    worker.task(
        task_type="prepare-information",
        variables_to_fetch=["caseId", "alertLevel", "refreshId", "locationId"],
    )(information_preparedness_task)
    worker.task(
        task_type="prepare-staff",
        variables_to_fetch=["caseId", "alertLevel", "refreshId", "locationId"],
    )(staff_preparedness_task)
    worker.task(
        task_type="send-preparedness-notice",
        variables_to_fetch=["caseId", "alertLevel", "refreshId", "locationId"],
    )(send_preparedness_notice_task)
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
