#!/usr/bin/env bash

# Runs staged preparedness forecasts through INFORMATION, STATE, OPERATIONAL,
# and then sends a clear forecast to remove the alert.

set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

usage() {
    cat <<'EOF'
Usage: PreparednessFlowTest.sh [--open-operate]

Run the preparedness flow test. Pass --open-operate to open Camunda Operate
before running the test.
EOF
}

fail() {
    printf 'FULL FLOW TEST FAILED: %s\n' "$1" >&2
    printf 'Check that the Docker Compose services are running and healthy.\n' >&2
    exit 1
}

for arg in "$@"; do
    case "$arg" in
        --open-operate)
            if command -v xdg-open >/dev/null 2>&1; then
                xdg-open 'http://localhost:8081' >/dev/null 2>&1 &
            elif command -v open >/dev/null 2>&1; then
                open 'http://localhost:8081' >/dev/null 2>&1 &
            else
                printf 'Open Camunda Operate at http://localhost:8081\n'
            fi
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage >&2
            exit 2
            ;;
    esac
done

for dependency in curl jq docker timeout; do
    command -v "$dependency" >/dev/null 2>&1 || fail "Required command not found: $dependency"
done

get_communication_logs() {
    local output_file error_file status
    output_file="$(mktemp)"
    error_file="$(mktemp)"
    (cd "$REPO_ROOT" && timeout 15s docker compose logs --since=2m --tail=100 communication) >"$output_file" 2>"$error_file"
    status=$?
    if (( status != 0 )); then
        if (( status == 124 )); then
            rm -f "$output_file" "$error_file"
            return 2
        fi
        GET_LOGS_ERROR="$(cat "$error_file")"
        rm -f "$output_file" "$error_file"
        return 1
    fi
    GET_LOGS_OUTPUT="$(cat "$output_file")"
    rm -f "$output_file" "$error_file"
    return 0
}

get_communication_snapshot() {
    get_communication_logs
    local logs_status=$?
    if (( logs_status != 0)); then
        case "$logs_status" in
            2) fail 'Timed out while reading communication logs.' ;;
            *) fail "Could not read Docker Compose logs: ${GET_LOGS_ERROR:-unknown error}" ;;
        esac
    fi

    SNAPSHOT_OUTPUT="$GET_LOGS_OUTPUT"
    SNAPSHOT_DECISION_COUNT="$(
        grep -Ec 'POST /preparedness_decision HTTP/1\.1" [0-9]{3}' <<<"$SNAPSHOT_OUTPUT" || true
    )"
    SNAPSHOT_TASK_COUNT="$(
        grep -Fc '[Camunda] Simulating' <<<"$SNAPSHOT_OUTPUT" || true
    )"
}

send_test_refresh() {
    local location_id="$1"
    local refresh_id="$2"
    local sea_level_cm="$3"
    local lead_time_hours="$4"
    local forecast_json policy_json request_body

    forecast_json="$(jq -cn \
        --arg location_id "$location_id" \
        --argjson sea_level_cm "$sea_level_cm" \
        --argjson lead_time_hours "$lead_time_hours" \
        '[{location_id:$location_id,
           sea_level_cm:$sea_level_cm,
           lead_time_hours:$lead_time_hours}]')"
    policy_json="$(jq -cn \
        --arg location_id "$location_id" \
        '{
          forecast_horizon_hours:36,
          information_lead_hours:6,
          state_lead_hours:4,
          operational_lead_hours:2,
          regions:{
            "test-region":{
              category_1_min_cm:100,
              category_2_min_cm:150,
              category_3_above_cm:200
            }
          },
          locations:{
            ($location_id):{region:"test-region"}
          }
        }')"
    request_body="$(jq -cn \
        --arg refresh_id "$refresh_id" \
        --arg location_id "$location_id" \
        --arg forecasts_json "$forecast_json" \
        --arg policy_json "$policy_json" \
        '{refresh_id:$refresh_id,
          location_id:$location_id,
          forecasts_json:$forecasts_json,
          policy_json:$policy_json}')"

    if ! curl --silent --show-error --fail --max-time 15 \
        -H 'Content-Type: application/json' \
        -d "$request_body" \
        http://localhost:7077/forecast-refreshes >/dev/null; then
        fail "Could not submit the forecast refresh $refresh_id to Siddhi."
    fi
}

wait_for_decision() {
    local baseline_count="$1"
    local stage_name="$2"
    local attempt snapshot_count decision_line status latest_decision_line=''

    for ((attempt=0; attempt<15; attempt++)); do
        sleep 2
        get_communication_snapshot
        snapshot_count="$SNAPSHOT_DECISION_COUNT"
        if (( snapshot_count > baseline_count )); then
            latest_decision_line=''
            while IFS= read -r decision_line; do
                if [[ "$decision_line" =~ POST\ /preparedness_decision\ HTTP/1\.1\"\ ([0-9]{3}) ]]; then
                    status="${BASH_REMATCH[1]}"
                    latest_decision_line="$decision_line"
                fi
            done <<<"$SNAPSHOT_OUTPUT"
            if [[ -n "$latest_decision_line" ]]; then
                if [[ "$status" != '200' ]]; then
                    fail "$stage_name decision was rejected: $latest_decision_line"
                fi
                printf '%s decision accepted: %s\n' "$stage_name" "$latest_decision_line"
                return 0
            fi
        fi
    done

    fail "Timed out waiting for communication to receive the $stage_name decision."
}

wait_for_camunda_tasks() {
    local baseline_task_count="$1"
    local stage_name="$2"
    shift 2
    local task_names=("$@")
    local attempt line task_name matched_count
    local -a new_task_lines=()
    local -a matched_lines=()

    for ((attempt=0; attempt<15; attempt++)); do
        get_communication_snapshot
        new_task_lines=()
        matched_lines=()

        mapfile -t all_task_lines < <(
            grep -F '[Camunda] Simulating' <<<"$SNAPSHOT_OUTPUT" || true
        )
        for ((line=baseline_task_count; line<${#all_task_lines[@]}; line++)); do
            new_task_lines+=("${all_task_lines[$line]}")
        done

        for task_name in "${task_names[@]}"; do
            matched_line=''
            for line in "${new_task_lines[@]}"; do
                if [[ "$line" == *"Simulating $task_name for case"* ]]; then
                    matched_line="$line"
                    break
                fi
            done
            if [[ -z "$matched_line" ]]; then
                matched_lines=()
                break
            fi
            matched_lines+=("$matched_line")
        done

        if (( ${#matched_lines[@]} == ${#task_names[@]} )); then
            printf '%s\n' "${matched_lines[@]}"
            sleep 1
            return 0
        fi
        sleep 2
    done

    fail "Timed out waiting for Camunda to run $stage_name."
}

if ! health_response="$(curl --silent --show-error --fail --max-time 5 http://localhost:5001/health 2>&1)"; then
    fail "Could not reach communication health endpoint: $health_response"
fi
health_status="$(jq -r '.status // empty' <<<"$health_response" 2>/dev/null)"
[[ "$health_status" == 'ok' ]] || fail "Communication is not ready (health status: ${health_status:-unknown})."

stamp="$(date +%Y%m%d%H%M%S)$(date +%N 2>/dev/null | cut -c1-3)"
location_id="e2e-test-$stamp"

sea_level_cm=$((150 + RANDOM % 51))
information_lead_hours=$((5 + RANDOM % 2))
state_lead_hours=$((3 + RANDOM % 2))
operational_lead_hours=$((RANDOM % 3))

printf 'Location: %s\n' "$location_id"
printf 'Randomized sea level: %s cm (CATEGORY_2)\n' "$sea_level_cm"
printf 'Running staged alert decisions and automatic clear...\n\n'

get_communication_snapshot
baseline_decision_count="$SNAPSHOT_DECISION_COUNT"
baseline_task_count="$SNAPSHOT_TASK_COUNT"

refresh_id="e2e-$stamp-information"
send_test_refresh "$location_id" "$refresh_id" "$sea_level_cm" "$information_lead_hours"
printf 'Sent INFORMATION forecast: %s cm at %s hours.\n' "$sea_level_cm" "$information_lead_hours"
wait_for_decision "$baseline_decision_count" 'INFORMATION'
wait_for_camunda_tasks "$baseline_task_count" 'INFORMATION' \
    'internalPreparedness' 'informationPreparedness'

get_communication_snapshot
baseline_decision_count="$SNAPSHOT_DECISION_COUNT"
baseline_task_count="$SNAPSHOT_TASK_COUNT"

refresh_id="e2e-$stamp-state"
send_test_refresh "$location_id" "$refresh_id" "$sea_level_cm" "$state_lead_hours"
printf 'Sent STATE forecast: %s cm at %s hours.\n' "$sea_level_cm" "$state_lead_hours"
wait_for_decision "$baseline_decision_count" 'STATE'
wait_for_camunda_tasks "$baseline_task_count" 'STATE' 'staffPreparedness'

get_communication_snapshot
baseline_decision_count="$SNAPSHOT_DECISION_COUNT"
baseline_task_count="$SNAPSHOT_TASK_COUNT"

refresh_id="e2e-$stamp-operational"
send_test_refresh "$location_id" "$refresh_id" "$sea_level_cm" "$operational_lead_hours"
printf 'Sent OPERATIONAL forecast: %s cm at %s hours.\n' "$sea_level_cm" "$operational_lead_hours"
wait_for_decision "$baseline_decision_count" 'OPERATIONAL'
wait_for_camunda_tasks "$baseline_task_count" 'OPERATIONAL' 'operationalPreparedness'

get_communication_snapshot
baseline_decision_count="$SNAPSHOT_DECISION_COUNT"

refresh_id="e2e-$stamp-clear"
send_test_refresh "$location_id" "$refresh_id" 99 1
printf 'Sent NONE forecast: 99 cm at 1 hour to clear the alert.\n'
wait_for_decision "$baseline_decision_count" 'clear/NONE'

printf '\nPASS: INFORMATION, STATE, OPERATIONAL, and NONE decisions were accepted; all preparedness tasks ran.\n'
printf 'The BPMN clear message was published. Open Operate to confirm the instance completed.\n'
