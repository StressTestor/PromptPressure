#!/usr/bin/env bash
# start litellm proxy for promptpressure
# runs on localhost:4000 with openai-compatible endpoint

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CONFIG="$PROJECT_ROOT/litellm_config.yaml"
PORT=4000
LOG="$PROJECT_ROOT/litellm.log"

if ! command -v litellm &>/dev/null; then
    echo "litellm not found. install with: pip install 'litellm[proxy]'"
    exit 1
fi

if [ ! -f "$CONFIG" ]; then
    echo "config not found: $CONFIG"
    exit 1
fi

# check if already running
if lsof -i ":$PORT" &>/dev/null; then
    echo "port $PORT already in use. litellm may already be running."
    echo "stop it with: kill \$(lsof -t -i :$PORT)"
    exit 1
fi

# check required env vars
missing=()
[ -z "${ANTHROPIC_API_KEY:-}" ] && missing+=("ANTHROPIC_API_KEY")
[ -z "${DEEPSEEK_API_KEY:-}" ] && missing+=("DEEPSEEK_API_KEY")
[ -z "${GOOGLE_API_KEY:-}" ] && missing+=("GOOGLE_API_KEY")
[ -z "${XAI_API_KEY:-}" ] && missing+=("XAI_API_KEY")

if [ ${#missing[@]} -gt 0 ]; then
    echo "warning: missing env vars: ${missing[*]}"
    echo "models using those keys will fail at request time."
fi

echo "starting litellm proxy on localhost:$PORT"
echo "config: $CONFIG"
echo "log: $LOG"

nohup litellm --config "$CONFIG" \
    --host 127.0.0.1 \
    --port "$PORT" \
    > "$LOG" 2>&1 &

PID=$!
echo "litellm started (pid $PID)"
echo "endpoint: http://localhost:$PORT/v1/chat/completions"
echo ""
echo "verify: curl http://localhost:$PORT/health"
echo "stop:   kill $PID"

# wait briefly and check it didn't crash on startup
sleep 2
if ! kill -0 "$PID" 2>/dev/null; then
    echo "litellm failed to start. check $LOG"
    tail -20 "$LOG"
    exit 1
fi
