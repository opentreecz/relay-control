#!/usr/bin/env python3
"""
relay-control — Flask application to control a GPIO relay via REST API.
GPIO BCM pin 17 (physical pin 11) outputs 3.3 V to drive the relay.
"""

import os
import csv
import json
import time
import logging
import threading
import functools
from datetime import datetime, timezone
from pathlib import Path

from flask import (
    Flask, jsonify, request, send_file, render_template,
    Response, abort
)

# ---------------------------------------------------------------------------
# Optional RPi.GPIO import — falls back to a stub when not on real hardware
# ---------------------------------------------------------------------------
try:
    import RPi.GPIO as GPIO
    ON_PI = True
except (ImportError, RuntimeError):
    ON_PI = False

    class _GPIOStub:
        BCM = "BCM"
        OUT = "OUT"
        HIGH = True
        LOW  = False
        _state: dict = {}

        def setmode(self, m):          pass
        def setwarnings(self, v):      pass
        def setup(self, pin, mode):    self._state[pin] = self.LOW
        def output(self, pin, val):    self._state[pin] = val
        def input(self, pin):          return self._state.get(pin, self.LOW)
        def cleanup(self):             pass

    GPIO = _GPIOStub()

# ---------------------------------------------------------------------------
# Configuration (override via environment variables)
# ---------------------------------------------------------------------------
RELAY_PIN       = int(os.getenv("RELAY_PIN",       "17"))
API_USERNAME    = os.getenv("API_USERNAME",         "admin")
API_PASSWORD    = os.getenv("API_PASSWORD",         "changeme")
LOG_DIR         = Path(os.getenv("LOG_DIR",         "/var/log/relay-control"))
SECRET_KEY      = os.getenv("SECRET_KEY",           "replace-with-a-real-secret")
DEACTIVATE_SECS = int(os.getenv("DEACTIVATE_SECS",  "10"))
HOST            = os.getenv("HOST",                 "0.0.0.0")
PORT            = int(os.getenv("PORT",             "5000"))

LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE  = LOG_DIR / "relay.log"
CSV_FILE  = LOG_DIR / "events.csv"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CSV event log helpers
# ---------------------------------------------------------------------------
CSV_HEADER = ["timestamp", "event", "pin", "state", "source", "details"]

def _ensure_csv():
    if not CSV_FILE.exists():
        with open(CSV_FILE, "w", newline="") as fh:
            csv.writer(fh).writerow(CSV_HEADER)

_ensure_csv()

def log_event(event: str, state: str, source: str = "system", details: str = ""):
    ts = datetime.now(timezone.utc).isoformat()
    row = [ts, event, RELAY_PIN, state, source, details]
    with open(CSV_FILE, "a", newline="") as fh:
        csv.writer(fh).writerow(row)
    logger.info("event=%s pin=%s state=%s source=%s details=%s",
                event, RELAY_PIN, state, source, details)

def read_events(limit: int = 100) -> list[dict]:
    if not CSV_FILE.exists():
        return []
    rows = []
    with open(CSV_FILE, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)
    return list(reversed(rows[-limit:]))

# ---------------------------------------------------------------------------
# GPIO initialisation
# ---------------------------------------------------------------------------
_relay_lock = threading.Lock()
_pulse_thread: threading.Thread | None = None

def gpio_init():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(RELAY_PIN, GPIO.OUT)
    GPIO.output(RELAY_PIN, GPIO.HIGH)   # active HIGH = relay ON at boot
    log_event("INIT", "ON", "system", "GPIO initialised — relay activated at startup")

def relay_state() -> str:
    return "ON" if GPIO.input(RELAY_PIN) else "OFF"

def set_relay(state: bool, source: str = "system", details: str = ""):
    with _relay_lock:
        GPIO.output(RELAY_PIN, GPIO.HIGH if state else GPIO.LOW)
        log_event("SET", "ON" if state else "OFF", source, details)

# ---------------------------------------------------------------------------
# Pulse procedure: OFF for DEACTIVATE_SECS seconds, then permanently ON
# ---------------------------------------------------------------------------
def _pulse_worker(source: str):
    logger.info("Pulse started — deactivating relay for %d s", DEACTIVATE_SECS)
    set_relay(False, source, f"Pulse OFF phase ({DEACTIVATE_SECS}s)")
    time.sleep(DEACTIVATE_SECS)
    set_relay(True, source, "Pulse ON phase (permanent)")
    logger.info("Pulse complete — relay reactivated")

def trigger_pulse(source: str = "api") -> dict:
    global _pulse_thread
    if _pulse_thread and _pulse_thread.is_alive():
        return {"ok": False, "message": "Pulse already in progress"}
    _pulse_thread = threading.Thread(target=_pulse_worker, args=(source,), daemon=True)
    _pulse_thread.start()
    return {"ok": True, "message": f"Pulse triggered — relay OFF for {DEACTIVATE_SECS}s"}

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = SECRET_KEY

# ---------------------------------------------------------------------------
# Basic Auth decorator
# ---------------------------------------------------------------------------
def require_auth(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.username != API_USERNAME or auth.password != API_PASSWORD:
            return Response(
                json.dumps({"error": "Unauthorized"}),
                401,
                {"WWW-Authenticate": 'Basic realm="Relay Control"',
                 "Content-Type": "application/json"},
            )
        return fn(*args, **kwargs)
    return wrapper

# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    """Health-check — no auth required."""
    return jsonify({
        "status": "ok",
        "relay_state": relay_state(),
        "pin": RELAY_PIN,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "on_pi": ON_PI,
    })


@app.get("/api/status")
@require_auth
def status():
    """Current relay state."""
    return jsonify({
        "relay_state": relay_state(),
        "pin": RELAY_PIN,
        "pulse_active": bool(_pulse_thread and _pulse_thread.is_alive()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.post("/api/trigger")
@require_auth
def trigger():
    """Trigger the deactivate-then-reactivate pulse."""
    source = request.authorization.username if request.authorization else "api"
    result = trigger_pulse(source)
    status_code = 200 if result["ok"] else 409
    return jsonify(result), status_code


@app.get("/api/events")
@require_auth
def events():
    """Return the last N events as JSON."""
    limit = min(int(request.args.get("limit", 100)), 1000)
    return jsonify({"events": read_events(limit)})


@app.get("/api/events/download")
@require_auth
def events_download():
    """Download the full events CSV."""
    if not CSV_FILE.exists():
        abort(404, "No events logged yet")
    return send_file(
        CSV_FILE,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"relay_events_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
    )


# ---------------------------------------------------------------------------
# Web UI
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return render_template("index.html",
                           username=API_USERNAME,
                           password=API_PASSWORD,
                           deactivate_secs=DEACTIVATE_SECS)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    gpio_init()
    try:
        app.run(host=HOST, port=PORT, debug=False, threaded=True)
    finally:
        GPIO.cleanup()
        logger.info("Application stopped — GPIO cleaned up")
