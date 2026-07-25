import datetime
from flask import Flask, jsonify, request
import temp
import temp_control
import os
from influxdb_client import InfluxDBClient, Point

app = Flask(__name__)

# Configuration
INFLUX_URL = "http://localhost:8086"
TOKEN = "<token>"  # Replace with your actual token
ORG = "demo"
DATA_FILE = os.path.join(os.path.dirname(__file__), 'data.csv')

# Initialize InfluxDB Client (do this once at startup)
client = InfluxDBClient(url=INFLUX_URL, token=TOKEN, org=ORG)
write_api = client.write_api()
query_api = client.query_api()

def log_to_file(timestamp, sensors):
    cutoff = datetime.datetime.now() - datetime.timedelta(hours=1)

    # Append new data
    with open(DATA_FILE, 'a') as f:
        for sensor_id, value in sensors.items():
            f.write(f'{timestamp},{sensor_id},{value:.2f}\n')

    # Prune old data (keep only past hour)
    with open(DATA_FILE, 'r') as f:
        lines = f.readlines()

    valid_lines = []
    for line in lines:
        try:
            line_ts_str = line.split(',')[0]
            line_ts = datetime.datetime.fromisoformat(line_ts_str)
            if line_ts >= cutoff:
                valid_lines.append(line)
        except (ValueError, IndexError):
            continue  # skip malformed lines

    with open(DATA_FILE, 'w') as f:
        f.writelines(valid_lines)

@app.route('/')
def index():
    return """
    <!doctype html>
    <html lang="en">
        <head>
            <meta charset="utf-8">
            <title>Temperature — Live Monitor</title>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                :root {
                    color-scheme: dark;
                    --bg: #000;
                    --surface: #0a0a0a;
                    --surface-raised: #111;
                    --border: #262626;
                    --border-strong: #3a3a3a;
                    --text: #f5f5f5;
                    --muted: #8a8a8a;
                    --subtle: #5f5f5f;
                    --danger: #ff6b6b;
                    --success: #8ee3b1;
                    --warning: #f2c66d;
                }
                * { box-sizing: border-box; }
                html { background: var(--bg); }
                body {
                    min-width: 320px;
                    min-height: 100vh;
                    margin: 0;
                    background: var(--bg);
                    color: var(--text);
                    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display",
                        "SF Pro Text", "Helvetica Neue", Arial, sans-serif;
                    -webkit-font-smoothing: antialiased;
                    text-rendering: optimizeLegibility;
                }
                button, input { font: inherit; }
                .container {
                    width: min(100%, 1680px);
                    margin: 0 auto;
                    padding: 28px 32px 40px;
                }
                .topbar {
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    gap: 24px;
                    min-height: 48px;
                    margin-bottom: 32px;
                }
                .brand {
                    display: flex;
                    align-items: baseline;
                    gap: 12px;
                }
                h1 {
                    margin: 0;
                    color: var(--text);
                    font-size: 20px;
                    font-weight: 600;
                    letter-spacing: -0.025em;
                }
                .brand-copy {
                    color: var(--subtle);
                    font-size: 13px;
                }
                #status {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    color: var(--muted);
                    font-size: 12px;
                    font-variant-numeric: tabular-nums;
                    white-space: nowrap;
                }
                #status::before {
                    width: 6px;
                    height: 6px;
                    border-radius: 50%;
                    background: #b7b7b7;
                    box-shadow: 0 0 0 3px rgba(183,183,183,0.1);
                    content: "";
                }
                #status.error { color: var(--danger); }
                #status.error::before {
                    background: var(--danger);
                    box-shadow: 0 0 0 3px rgba(255,107,107,0.12);
                }
                .control {
                    display: grid;
                    grid-template-columns: minmax(190px, 1fr) auto;
                    align-items: center;
                    gap: 24px;
                    margin-bottom: 20px;
                    padding: 18px 20px;
                    border: 1px solid var(--border);
                    border-radius: 16px;
                    background: var(--surface);
                }
                .control-copy {
                    min-width: 0;
                }
                .control h2 {
                    margin: 0 0 6px;
                    color: var(--text);
                    font-size: 14px;
                    font-weight: 550;
                    letter-spacing: -0.01em;
                }
                #ctrlStatus {
                    overflow: hidden;
                    color: var(--muted);
                    font-size: 12px;
                    font-variant-numeric: tabular-nums;
                    line-height: 1.35;
                    text-overflow: ellipsis;
                    white-space: nowrap;
                }
                #ctrlStatus .state { color: var(--text); font-weight: 550; }
                #ctrlStatus.heating .state { color: var(--warning); }
                #ctrlStatus.holding .state { color: var(--success); }
                #ctrlStatus.fault .state { color: var(--danger); }
                .control-row {
                    display: flex;
                    align-items: flex-end;
                    gap: 8px;
                }
                .field {
                    display: grid;
                    gap: 7px;
                }
                .field label {
                    padding-left: 2px;
                    color: var(--subtle);
                    font-size: 10px;
                    font-weight: 600;
                    letter-spacing: 0.08em;
                    text-transform: uppercase;
                }
                .control input {
                    width: 132px;
                    height: 38px;
                    padding: 0 12px;
                    border: 1px solid var(--border);
                    border-radius: 9px;
                    outline: none;
                    background: var(--surface-raised);
                    color: var(--text);
                    font-size: 13px;
                    font-variant-numeric: tabular-nums;
                    transition: border-color 140ms ease, box-shadow 140ms ease;
                }
                .control input::placeholder { color: #545454; }
                .control input:focus {
                    border-color: #707070;
                    box-shadow: 0 0 0 3px rgba(255,255,255,0.08);
                }
                .control button {
                    height: 38px;
                    padding: 0 17px;
                    border: 1px solid transparent;
                    border-radius: 9px;
                    font-size: 13px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: background 140ms ease, border-color 140ms ease,
                        color 140ms ease, opacity 140ms ease;
                }
                .control button:focus-visible {
                    outline: 2px solid #fff;
                    outline-offset: 2px;
                }
                .control button:disabled { opacity: 0.28; cursor: default; }
                #startBtn { background: #f2f2f2; color: #080808; }
                #startBtn:not(:disabled):hover { background: #fff; }
                #stopBtn {
                    border-color: var(--border-strong);
                    background: transparent;
                    color: #d8d8d8;
                }
                #stopBtn:not(:disabled):hover { border-color: #626262; color: #fff; }
                .sensors {
                    display: grid;
                    grid-template-columns: minmax(0, 1fr);
                    gap: 20px;
                }
                .card {
                    min-width: 0;
                    padding: 26px 28px 22px;
                    border: 1px solid var(--border);
                    border-radius: 20px;
                    background: var(--surface);
                }
                .card-header {
                    display: flex;
                    align-items: flex-end;
                    justify-content: space-between;
                    gap: 28px;
                    margin-bottom: 16px;
                }
                .sensor-meta { min-width: 0; }
                .eyebrow {
                    margin: 0 0 9px;
                    color: var(--subtle);
                    font-size: 10px;
                    font-weight: 650;
                    letter-spacing: 0.1em;
                    text-transform: uppercase;
                }
                .card h2 {
                    overflow: hidden;
                    margin: 0;
                    color: var(--muted);
                    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco,
                        Consolas, "Liberation Mono", monospace;
                    font-size: 12px;
                    font-weight: 400;
                    line-height: 1.4;
                    text-overflow: ellipsis;
                    white-space: nowrap;
                }
                .temp {
                    flex: 0 0 auto;
                    color: var(--text);
                    font-size: clamp(52px, 6vw, 88px);
                    font-weight: 520;
                    font-variant-numeric: tabular-nums;
                    letter-spacing: -0.065em;
                    line-height: 0.88;
                    white-space: nowrap;
                }
                .temp-unit {
                    margin-left: 6px;
                    color: var(--muted);
                    font-size: 0.36em;
                    font-weight: 450;
                    letter-spacing: -0.02em;
                    vertical-align: top;
                }
                .chart-wrap {
                    position: relative;
                    width: 100%;
                    height: clamp(380px, 58vh, 720px);
                }
                @media (max-width: 820px) {
                    .container { padding: 22px 18px 28px; }
                    .topbar { align-items: flex-start; margin-bottom: 24px; }
                    .brand { display: grid; gap: 4px; }
                    .control { grid-template-columns: 1fr; gap: 18px; }
                    .control-row { width: 100%; }
                    .field { flex: 1 1 120px; }
                    .control input { width: 100%; }
                    .card { padding: 22px 20px 18px; border-radius: 16px; }
                    .chart-wrap { height: clamp(340px, 52vh, 560px); }
                }
                @media (max-width: 560px) {
                    .topbar { gap: 14px; }
                    .brand-copy { display: none; }
                    #status { max-width: 52%; white-space: normal; }
                    .control-row { display: grid; grid-template-columns: 1fr 1fr; }
                    .control button { width: 100%; }
                    .card-header { display: grid; gap: 24px; }
                    .temp { grid-row: 1; }
                    .sensor-meta { grid-row: 2; }
                    .chart-wrap { height: 360px; }
                }
            </style>
        </head>
        <body>
            <main class="container">
                <header class="topbar">
                    <div class="brand">
                        <h1>Temperature</h1>
                        <span class="brand-copy">Live thermal monitor</span>
                    </div>
                    <div id="status" role="status" aria-live="polite">Connecting...</div>
                </header>
                <div class="control">
                    <div class="control-copy">
                        <h2>Hot plate control</h2>
                        <div id="ctrlStatus" aria-live="polite"><span class="state">Idle</span></div>
                    </div>
                    <div class="control-row">
                        <div class="field">
                            <label for="targetInput">Target</label>
                            <input id="targetInput" type="number" step="0.5" min="1" max="110" placeholder="Temperature °C">
                        </div>
                        <div class="field">
                            <label for="minutesInput">Hold time</label>
                            <input id="minutesInput" type="number" step="1" min="1" placeholder="Optional minutes">
                        </div>
                        <button id="startBtn">Start</button>
                        <button id="stopBtn" disabled>Stop</button>
                    </div>
                </div>
                <div id="sensors" class="sensors"></div>
            </main>

            <script>
                // One Chart instance per sensor id.
                const charts = {};

                function ensureCard(sensorId) {
                    if (charts[sensorId]) return charts[sensorId];

                    const card = document.createElement('div');
                    card.className = 'card';
                    card.innerHTML =
                        '<div class="card-header">' +
                            '<div class="sensor-meta">' +
                                '<p class="eyebrow">Live reading</p>' +
                                '<h2></h2>' +
                            '</div>' +
                            '<div class="temp"><span class="temp-value">--</span>' +
                                '<span class="temp-unit">°C</span></div>' +
                        '</div>' +
                        '<div class="chart-wrap"><canvas></canvas></div>';
                    card.querySelector('h2').textContent = sensorId;
                    document.getElementById('sensors').appendChild(card);

                    const chart = new Chart(card.querySelector('canvas').getContext('2d'), {
                        type: 'line',
                        data: {
                            labels: [],
                            datasets: [{
                                label: 'Temperature (°C)',
                                data: [],
                                borderColor: '#f0f0f0',
                                backgroundColor: 'rgba(255, 255, 255, 0.035)',
                                borderWidth: 2.25,
                                fill: true,
                                tension: 0.32,
                                pointRadius: 0,
                                pointHoverRadius: 4,
                                pointHoverBackgroundColor: '#ffffff',
                                pointHoverBorderColor: '#0a0a0a',
                                pointHoverBorderWidth: 2
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            animation: false,
                            interaction: {
                                mode: 'index',
                                intersect: false
                            },
                            layout: {
                                padding: { top: 10, right: 8, bottom: 0, left: 0 }
                            },
                            scales: {
                                x: {
                                    border: { display: false },
                                    ticks: {
                                        color: '#686868',
                                        font: { size: 10 },
                                        maxTicksLimit: 8,
                                        maxRotation: 0
                                    },
                                    grid: { display: false }
                                },
                                y: {
                                    border: { display: false },
                                    ticks: {
                                        color: '#686868',
                                        font: { size: 10 },
                                        maxTicksLimit: 6,
                                        padding: 10,
                                        callback: value => value + '°'
                                    },
                                    grid: {
                                        color: 'rgba(255,255,255,0.07)',
                                        drawTicks: false
                                    }
                                }
                            },
                            plugins: {
                                legend: { display: false },
                                tooltip: {
                                    backgroundColor: '#f2f2f2',
                                    titleColor: '#686868',
                                    bodyColor: '#090909',
                                    borderWidth: 0,
                                    padding: 12,
                                    displayColors: false,
                                    titleFont: { size: 11, weight: 'normal' },
                                    bodyFont: { size: 14, weight: 'bold' },
                                    callbacks: {
                                        label: context => context.parsed.y.toFixed(2) + ' °C'
                                    }
                                }
                            }
                        }
                    });

                    charts[sensorId] = { chart, temp: card.querySelector('.temp-value') };
                    return charts[sensorId];
                }

                function setStatus(text, isError) {
                    const status = document.getElementById('status');
                    status.textContent = text;
                    status.className = isError ? 'error' : '';
                }

                function renderControl(ctrl) {
                    const el = document.getElementById('ctrlStatus');
                    const active = ctrl.state === 'heating' || ctrl.state === 'holding';
                    document.getElementById('startBtn').disabled = active;
                    document.getElementById('stopBtn').disabled = !active;
                    el.className = ctrl.state;

                    let text = '<span class="state">' +
                        ctrl.state.charAt(0).toUpperCase() + ctrl.state.slice(1) +
                        '</span>';
                    if (ctrl.target_c !== undefined && ctrl.target_c !== null) {
                        text += ' &nbsp;·&nbsp; target ' + ctrl.target_c.toFixed(1) + ' °C';
                    }
                    if (active) {
                        text += ' &nbsp;·&nbsp; duty ' + Math.round(ctrl.duty * 100) + '%';
                    }
                    if (ctrl.state === 'holding' && ctrl.hold_elapsed_s !== null) {
                        text += ' &nbsp;·&nbsp; held ' + Math.floor(ctrl.hold_elapsed_s / 60) +
                            'm ' + Math.floor(ctrl.hold_elapsed_s % 60) + 's';
                        if (ctrl.hold_minutes) text += ' / ' + ctrl.hold_minutes + 'm';
                    }
                    if (ctrl.state === 'fault' && ctrl.error) {
                        text += ' &nbsp;·&nbsp; ' + ctrl.error;
                    }
                    el.innerHTML = text;
                }

                async function startControl() {
                    const target = parseFloat(document.getElementById('targetInput').value);
                    if (isNaN(target)) { alert('Enter a target temperature'); return; }
                    const minsRaw = document.getElementById('minutesInput').value;
                    const body = { target_c: target };
                    if (minsRaw !== '') body.minutes = parseFloat(minsRaw);
                    const response = await fetch('/api/control/start', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(body)
                    });
                    const data = await response.json();
                    if (!response.ok) { alert(data.error); return; }
                    renderControl(data);
                }

                async function stopControl() {
                    const response = await fetch('/api/control/stop', { method: 'POST' });
                    renderControl(await response.json());
                }

                document.getElementById('startBtn').addEventListener('click', startControl);
                document.getElementById('stopBtn').addEventListener('click', stopControl);

                async function updateTemp() {
                    try {
                        const response = await fetch('/api/temperature');
                        if (!response.ok) throw new Error('Server error');
                        const data = await response.json();

                        if (data.control) renderControl(data.control);

                        const timeLabel = new Date(data.timestamp).toLocaleTimeString();
                        for (const [sensorId, value] of Object.entries(data.sensors)) {
                            const { chart, temp } = ensureCard(sensorId);
                            temp.textContent = value.toFixed(2);

                            chart.data.labels.push(timeLabel);
                            chart.data.datasets[0].data.push(value);

                            // Keep only last 300 points (10 min at 2-second intervals)
                            if (chart.data.labels.length > 300) {
                                chart.data.labels.shift();
                                chart.data.datasets[0].data.shift();
                            }
                            chart.update('none'); // 'none' mode for performance
                        }
                        setStatus('Last updated: ' + timeLabel, false);
                    } catch (e) {
                        setStatus('Error: ' + e.message, true);
                    }
                }

                async function loadHistory() {
                    try {
                        const response = await fetch('/api/history');
                        if (!response.ok) throw new Error('Failed to load history');
                        const data = await response.json();

                        for (const [sensorId, points] of Object.entries(data)) {
                            const { chart } = ensureCard(sensorId);
                            chart.data.labels = points.map(d =>
                                new Date(d.timestamp).toLocaleTimeString()
                            );
                            chart.data.datasets[0].data = points.map(d => d.temperature);
                            chart.update();
                        }
                    } catch (e) {
                        console.error('Failed to load history:', e);
                    }
                }

                // Load initial history, then update every 2 seconds
                loadHistory();
                updateTemp();
                setInterval(updateTemp, 2000);
            </script>
        </body>
    </html>
    """

@app.route('/api/temperature')
def api_temperature():
    try:
        readings = temp.read_all()
        timestamp = datetime.datetime.now().isoformat()
        control = temp_control.controller.status()

        points = [
            Point("sensor").tag("sensor_id", sensor_id).field("temperature", value)
            for sensor_id, value in readings.items()
        ]

        # While a control run is active, log its setpoint and duty too
        log_rows = dict(readings)
        if control["state"] in ("heating", "holding"):
            points.append(
                Point("control")
                .field("setpoint", float(control["target_c"]))
                .field("duty", float(control["duty"]))
            )
            log_rows["setpoint"] = float(control["target_c"])
            log_rows["duty"] = float(control["duty"])

        if points:
            write_api.write(bucket="thermochromic", record=points)

        # Log to local data file
        log_to_file(timestamp, log_rows)

        return jsonify({
            "timestamp": timestamp,
            "sensors": readings,
            "control": control,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/control/status')
def api_control_status():
    return jsonify(temp_control.controller.status())

@app.route('/api/control/start', methods=['POST'])
def api_control_start():
    try:
        body = request.get_json(force=True)
        target_c = body["target_c"]
        minutes = body.get("minutes")  # None -> hold until stopped
        temp_control.controller.start(target_c, minutes)
        return jsonify(temp_control.controller.status())
    except (KeyError, ValueError, RuntimeError, TypeError) as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/control/stop', methods=['POST'])
def api_control_stop():
    temp_control.controller.stop()
    return jsonify(temp_control.controller.status())

@app.route('/api/history')
def api_history():
    try:
        flux_query = '''
            from(bucket: "thermochromic")
                |> range(start: -10m)
                |> filter(fn: (r) => r["_measurement"] == "sensor")
                |> filter(fn: (r) => r["_field"] == "temperature")
                |> sort(columns: ["_time"])
        '''

        result = query_api.query(flux_query, org=ORG)

        history = {}
        for table in result:
            for record in table.records:
                sensor_id = record.values.get("sensor_id", "unknown")
                history.setdefault(sensor_id, []).append({
                    "temperature": record["_value"],
                    "timestamp": record["_time"].isoformat()
                })

        return jsonify(history)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Starting web server...")
    app.run(host='0.0.0.0', port=5000)
