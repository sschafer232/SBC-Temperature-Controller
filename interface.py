from flask import Flask, jsonify
import temp  # Assuming this is your custom module with read_temp()
from influxdb_client import InfluxDBClient, Point

app = Flask(__name__)

# Configuration (from your original code)
INFLUX_URL = "http://localhost:8086"
TOKEN = "<token>"  # Replace with your actual token
ORG = "demo"

# Initialize InfluxDB Client (do this once at startup)
client = InfluxDBClient(url=INFLUX_URL, token=TOKEN, org=ORG)
write_api = client.write_api()
query_api = client.query_api()

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
                    max-width: 800px;
                    width: 100%;
                }
                h1 { margin: 0 0 20px; font-size: 24px; color: #eee; }
                .temp { font-size: 72px; font-weight: bold; color: #e94560; }
                .status { margin-top: 15px; font-size: 14px; color: #aaa; }
                .error { color: #e94560; font-size: 16px; }
                .chart-container {
                    margin-top: 30px;
                    background: #0f3460;
                    padding: 20px;
                    border-radius: 8px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Temperature Monitor</h1>
                <div id="temp-display" class="temp">-- °C</div>
                <div id="status" class="status">Connecting...</div>

                <div class="chart-container">
                    <canvas id="tempChart"></canvas>
                </div>
            </div>

            <script>
                const ctx = document.getElementById('tempChart').getContext('2d');
                let chart = new Chart(ctx, {
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
                            pointRadius: 3,
                            pointBackgroundColor: '#e94560'
                        }]
                    },
                    options: {
                        responsive: true,
                        scales: {
                            x: {
                                ticks: { color: '#aaa' },
                                grid: { color: 'rgba(255,255,255,0.1)' }
                            },
                            y: {
                                ticks: { color: '#aaa' },
                                grid: { color: 'rgba(255,255,255,0.1)' }
                            }
                        },
                        plugins: {
                            legend: { labels: { color: '#eee' } }
                        }
                    }
                });

                async function updateTemp() {
                    try {
                        const response = await fetch('/api/temperature');
                        if (!response.ok) throw new Error('Server error');
                        const data = await response.json();

                        document.getElementById('temp-display').textContent = 
                            data.temperature.toFixed(2) + ' °C';
                        document.getElementById('status').textContent = 
                            'Last updated: ' + new Date(data.timestamp).toLocaleTimeString();
                        document.getElementById('status').className = 'status';

                        // Update chart with latest data point
                        const timeLabel = new Date(data.timestamp).toLocaleTimeString();
                        chart.data.labels.push(timeLabel);
                        chart.data.datasets[0].data.push(data.temperature);

                        // Keep only last 300 data points (10 minutes at 2-second intervals)
                        if (chart.data.labels.length > 300) {
                            chart.data.labels.shift();
                            chart.data.datasets[0].data.shift();
                        }

                        chart.update('none'); // 'none' mode for performance
                    } catch (e) {
                        document.getElementById('temp-display').textContent = 'N/A';
                        document.getElementById('status').textContent = 
                            'Error: ' + e.message;
                        document.getElementById('status').className = 'error';
                    }
                }

                async function loadHistory() {
                    try {
                        const response = await fetch('/api/history');
                        if (!response.ok) throw new Error('Failed to load history');
                        const data = await response.json();

                        chart.data.labels = data.map(d => 
                            new Date(d.timestamp).toLocaleTimeString()
                        );
                        chart.data.datasets[0].data = data.map(d => d.temperature);
                        chart.update();
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
        current_temp = temp.read_temp()

        point = Point("sensor") \
            .tag("zone", 3) \
            .field("temperature", current_temp)
        write_api.write(bucket="thermochromic", record=point)   

        return jsonify({
            "temperature": current_temp,
            "timestamp": __import__('datetime').datetime.now().isoformat()
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
                |> filter(fn: (r) => r["zone"] == "3")
                |> sort(columns: ["_time"])
        '''
        
        result = query_api.query(flux_query, org=ORG)
        
        history = []
        for table in result:
            for record in table.records:
                history.append({
                    "temperature": record["_value"],
                    "timestamp": record["_time"].isoformat()
                })

        return jsonify(history)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Starting web server...")
    app.run(host='0.0.0.0', port=5000)
