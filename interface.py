import datetime
from flask import Flask, jsonify
import temp
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
    <html>
        <head>
            <title>Temperature Monitor</title>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    margin: 0;
                    background-color: #1a1a2e;
                    color: #eee;
                }
                .container {
                    text-align: center;
                    background: #16213e;
                    padding: 40px 60px;
                    border-radius: 12px;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                    max-width: 900px;
                    width: 100%;
                }
                h1 { margin: 0 0 20px; font-size: 24px; color: #eee; }
                #status { margin-bottom: 20px; font-size: 14px; color: #aaa; }
                #status.error { color: #e94560; }
                .sensors {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
                    gap: 20px;
                }
                .card {
                    background: #0f3460;
                    padding: 20px;
                    border-radius: 8px;
                }
                .card h2 {
                    margin: 0 0 10px;
                    font-size: 13px;
                    font-weight: normal;
                    color: #aaa;
                    word-break: break-all;
                }
                .temp { font-size: 56px; font-weight: bold; color: #e94560; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Temperature Monitor</h1>
                <div id="status">Connecting...</div>
                <div id="sensors" class="sensors"></div>
            </div>

            <script>
                // One Chart instance per sensor id.
                const charts = {};

                function ensureCard(sensorId) {
                    if (charts[sensorId]) return charts[sensorId];

                    const card = document.createElement('div');
                    card.className = 'card';
                    card.innerHTML =
                        '<h2>' + sensorId + '</h2>' +
                        '<div class="temp">-- °C</div>' +
                        '<canvas></canvas>';
                    document.getElementById('sensors').appendChild(card);

                    const chart = new Chart(card.querySelector('canvas').getContext('2d'), {
                        type: 'line',
                        data: {
                            labels: [],
                            datasets: [{
                                label: 'Temperature (°C)',
                                data: [],
                                borderColor: '#e94560',
                                backgroundColor: 'rgba(233, 69, 96, 0.1)',
                                borderWidth: 2,
                                fill: true,
                                tension: 0.3,
                                pointRadius: 2,
                                pointBackgroundColor: '#e94560'
                            }]
                        },
                        options: {
                            responsive: true,
                            scales: {
                                x: { ticks: { color: '#aaa' }, grid: { color: 'rgba(255,255,255,0.1)' } },
                                y: { ticks: { color: '#aaa' }, grid: { color: 'rgba(255,255,255,0.1)' } }
                            },
                            plugins: { legend: { labels: { color: '#eee' } } }
                        }
                    });

                    charts[sensorId] = { chart, temp: card.querySelector('.temp') };
                    return charts[sensorId];
                }

                function setStatus(text, isError) {
                    const status = document.getElementById('status');
                    status.textContent = text;
                    status.className = isError ? 'error' : '';
                }

                async function updateTemp() {
                    try {
                        const response = await fetch('/api/temperature');
                        if (!response.ok) throw new Error('Server error');
                        const data = await response.json();

                        const timeLabel = new Date(data.timestamp).toLocaleTimeString();
                        for (const [sensorId, value] of Object.entries(data.sensors)) {
                            const { chart, temp } = ensureCard(sensorId);
                            temp.textContent = value.toFixed(2) + ' °C';

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

        points = [
            Point("sensor").tag("sensor_id", sensor_id).field("temperature", value)
            for sensor_id, value in readings.items()
        ]
        if points:
            write_api.write(bucket="thermochromic", record=points)
        
        # Log to local data file
        log_to_file(timestamp, readings)
        
        return jsonify({
            "timestamp": timestamp,
            "sensors": readings,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
