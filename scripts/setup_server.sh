#!/usr/bin/env bash
# WikiMovieRec server setup (Ubuntu 24.04, Python 3.12)
# Run: bash scripts/setup_server.sh
set -euo pipefail

APP_DIR="/root/WikiMovieRec"
VENV="$APP_DIR/.venv"
SERVICE="wikimovierec"
PORT="${WIKIMODREC_PORT:-5041}"

cd "$APP_DIR"

echo "=== 1. System packages ==="
apt-get update -qq
apt-get install -y -qq python3.12-venv python3-pip >/dev/null
echo "OK"

echo "=== 2. Virtualenv ==="
if [ ! -d "$VENV" ]; then
    python3.12 -m venv "$VENV"
fi
"$VENV/bin/pip" install --upgrade pip wheel setuptools >/dev/null
echo "OK"

echo "=== 3. Dependencies (FastAPI + TensorFlow/Keras) ==="
"$VENV/bin/pip" install -r requirements.txt -r requirements-keras.txt
echo "OK"

echo "=== 4. Verify ==="
"$VENV/bin/python" -c "import fastapi, uvicorn, sklearn, numpy, pandas, tensorflow, keras; print('deps OK, TF', tensorflow.__version__)"

echo "=== 5. systemd service ==="
cat > /etc/systemd/system/${SERVICE}.service <<EOF
[Unit]
Description=WikiMovieRec API Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${APP_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=WIKIMODREC_PRESET=fast
Environment=WIKIMODREC_BACKEND=keras
Environment=WIKIMODREC_SOURCE=imdb
ExecStart=${VENV}/bin/python -m uvicorn src.api:create_app --host 0.0.0.0 --port ${PORT}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ${SERVICE}
echo "Service ${SERVICE} enabled (port ${PORT})"

echo "=== 6. Start ==="
systemctl restart ${SERVICE}
sleep 5
systemctl status ${SERVICE} --no-pager | head -15

echo "=== 7. Health check ==="
sleep 30
curl -s "http://127.0.0.1:${PORT}/api/health" || echo "HEALTH CHECK FAILED (model may still be loading, retry in 60s)"

echo ""
echo "=== DONE ==="
echo "API: http://<server-ip>:${PORT}"
echo "Logs: journalctl -u ${SERVICE} -f"
