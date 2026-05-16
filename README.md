# relay-control

Control a power relay via a Raspberry Pi GPIO pin.
Provides a REST API with Basic Auth, a web dashboard, event logging, and systemd integration.

---

## Hardware \Uffffffff GPIO Pin Selection

The application uses **GPIO 17 (BCM)**, physical pin 11.

```
Raspberry Pi GPIO header (40-pin)
---------------------------------
 3V3  (1) (2)  5V
GPIO2 (3) (4)  5V
GPIO3 (5) (6)  GND
GPIO4 (7) (8)  GPIO14
 GND  (9) (10) GPIO15
GPIO17(11)? OUTPUT (3.3 V)
GPIO18(12)    ...
```

**Why GPIO 17?**
- General-purpose, available on all 40-pin Pi models.
- Not used by SPI, I\UffffffffC, UART, or PWM by default.
- 3.3 V HIGH output \Uffffffff sufficient to drive a relay module with an optocoupler
  (typical threshold 1.2\Uffffffff2.5 V on IN pin). No level shifter needed.

**Relay wiring:**
```
Pi GPIO 17 (pin 11)  --?  Relay IN
Pi GND       (pin 9)  --?  Relay GND
Pi 5 V       (pin 4)  --?  Relay VCC   (most relay modules need 5 V on VCC)
```

> ??  Never drive inductive loads (motors, solenoids) directly. Always use a
> relay module with an optocoupler and a flyback diode.

---

## Logic: Startup & Pulse

| Event              | Relay state |
|--------------------|-------------|
| Application starts | **ON**      |
| `POST /api/trigger`| OFF for `DEACTIVATE_SECS` seconds (default 10), then permanently **ON** |

---

## Installation

```bash
# On the Raspberry Pi
git clone https://github.com/your-org/relay-control /tmp/relay-control
cd /tmp/relay-control
sudo bash install.sh
```

The installer:
1. Creates `/opt/relay-control` with a Python virtualenv
2. Creates `/var/log/relay-control` for logs and events CSV
3. Writes `/etc/relay-control/env` (credentials) \Uffffffff **edit this file**
4. Installs and enables `relay-control.service` in systemd

### Change credentials before first start

```bash
sudo nano /etc/relay-control/env
# Set API_USERNAME, API_PASSWORD, SECRET_KEY
sudo systemctl restart relay-control
```

---

## Configuration

All settings are environment variables (defined in `/etc/relay-control/env`):

| Variable          | Default    | Description                              |
|-------------------|------------|------------------------------------------|
| `RELAY_PIN`       | `17`       | BCM GPIO pin number                      |
| `API_USERNAME`    | `admin`    | Basic-auth username                      |
| `API_PASSWORD`    | `changeme` | Basic-auth password \Uffffffff **change this**    |
| `SECRET_KEY`      | (insecure) | Flask session secret \Uffffffff **change this**   |
| `DEACTIVATE_SECS` | `10`       | OFF duration during pulse (seconds)      |
| `LOG_DIR`         | `/var/log/relay-control` | Log and CSV directory     |
| `HOST`            | `0.0.0.0`  | Listening interface                      |
| `PORT`            | `5000`     | Listening port                           |

---

## API Reference

All endpoints except `/api/health` require **HTTP Basic Auth**.

### `GET /api/health`
No authentication. Returns service liveness.
```json
{ "status": "ok", "relay_state": "ON", "pin": 17, "timestamp": "\Uffffffff", "on_pi": true }
```

### `GET /api/status`
```json
{ "relay_state": "ON", "pin": 17, "pulse_active": false, "timestamp": "\Uffffffff" }
```

### `POST /api/trigger`
Starts the pulse sequence (OFF ? wait ? ON).
Returns `409` if a pulse is already in progress.
```json
{ "ok": true, "message": "Pulse triggered \Uffffffff relay OFF for 10s" }
```

### `GET /api/events?limit=100`
Returns the last N events as JSON.
```json
{ "events": [ { "timestamp": "\Uffffffff", "event": "SET", "pin": "17", "state": "ON", "source": "admin", "details": "\Uffffffff" } ] }
```

### `GET /api/events/download`
Downloads the full `events.csv` file.

---

## Web Dashboard

Open `http://<pi-ip>:5000` in a browser.

Features:
- Live relay status orb (green = ON, red = OFF, amber = pulse in progress)
- Countdown timer during pulse sequence
- Trigger button (disabled during active pulse)
- Scrollable event log table (auto-refreshes every 5 s)
- One-click CSV download

---

## systemd

```bash
# Check status
sudo systemctl status relay-control

# Live logs
sudo journalctl -u relay-control -f

# Restart
sudo systemctl restart relay-control

# Stop
sudo systemctl stop relay-control

# Disable autostart
sudo systemctl disable relay-control
```

---

## Development (without hardware)

The app runs on any machine without a Raspberry Pi.
`RPi.GPIO` is replaced by an in-memory stub automatically when the library
is not installed or not running on Pi hardware.

```bash
python3 -m venv venv
source venv/bin/activate
pip install flask
python app.py
# Open http://localhost:5000
```

---

## Security notes

- Credentials are stored in `/etc/relay-control/env` (readable by `root` and `pi` only).
- For production, put the application behind a reverse proxy (nginx/caddy) with TLS.
- The web UI embeds credentials in the HTML for convenience \Uffffffff in a production
  deployment use a proper session/cookie auth flow instead.
- Rate-limiting the `/api/trigger` endpoint is recommended for internet-facing deployments.

---

## File layout

```
relay-control/
+-- app.py                  # Main application
+-- requirements.txt        # Python dependencies
+-- templates/
\Uffffffff   +-- index.html          # Web dashboard
+-- relay-control.service   # systemd unit file
+-- env.example             # Environment template
+-- install.sh              # Deployment script
+-- README.md
```
