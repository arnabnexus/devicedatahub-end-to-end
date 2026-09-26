#!/usr/bin/env bash
set -Eeuo pipefail

PID_FILE="$1"
shift

forward_pid=""
stop_forward() {
    local exit_code=$?
    trap - EXIT INT TERM
    if [[ -n "$forward_pid" ]]; then
        kill "$forward_pid" >/dev/null 2>&1 || true
        wait "$forward_pid" >/dev/null 2>&1 || true
    fi
    rm -f "$PID_FILE"
    exit "$exit_code"
}

printf '%s\n' "$$" >"$PID_FILE"
trap stop_forward EXIT INT TERM
"$@" &
forward_pid=$!
wait "$forward_pid"
