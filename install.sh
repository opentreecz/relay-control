#!/usr/bin/env bash
# install.sh — deploy relay-control on Raspberry Pi OS (Bookworm / Bullseye)
# Run as root:  sudo bash install.sh
set -euo pipefail

APP_DIR=/opt/relay-control
LOG_DIR=/var/log/relay-control
CONF_DIR=/etc/relay-control
SERVICE_FILE=/etc/systemd/system/relay-control.service
APP_USER=pi

echo "▶ Installing relay-control …"

# ── 1. System packages ──────────────────────────────────────
apt-get update -qq
apt-get install -y python3 python3-venv python3-pip rsync sudo

# ── 2. Application files ────────────────────────────────────
install -d "$APP_DIR"
rsync -a --exclude '.git' --exclude '__pycache__' \
      --exclude 'venv' --exclude '*.pyc' \
      ./ "$APP_DIR/"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# ── 3. Python virtual environment ──────────────────────────
sudo -u "$APP_USER" python3 -m venv "$APP_DIR/venv"
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --quiet \
      flask RPi.GPIO

# ── 4. Log directory ────────────────────────────────────────
install -d -o "$APP_USER" -g "$APP_USER" -m 750 "$LOG_DIR"

# ── 5. Config directory (credentials) ──────────────────────
install -d -o root -g "$APP_USER" -m 750 "$CONF_DIR"
if [[ ! -f "$CONF_DIR/env" ]]; then
  install -o root -g "$APP_USER" -m 640 env.example "$CONF_DIR/env"
  echo ""
  echo "  ⚠  Edit $CONF_DIR/env to set a strong password and secret key"
  echo "     before starting the service."
  echo ""
fi

# ── 6. systemd service ──────────────────────────────────────
install -m 644 relay-control.service "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable relay-control
systemctl restart relay-control

echo ""
echo "✅  relay-control installed and started."
echo "    Status : sudo systemctl status relay-control"
echo "    Logs   : sudo journalctl -u relay-control -f"
echo "    Web UI : http://$(hostname -I | awk '{print $1}'):5000"
