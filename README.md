# pi5_ds18b20_demo
Temperature monitoring and control application using DS18B20 sensor. Features a live graph of observed temperatures over a period of 10 minutes.

<img width="882" height="660" alt="temp_monitor" src="https://github.com/user-attachments/assets/cf0dce22-0f66-459d-9a94-fe3ec3a81425" />

## Multiple sensors

<img width="2028" height="1682" alt="image" src="https://github.com/user-attachments/assets/13270391-c707-42a7-a79f-29ace7db4564" />

<img width="1024" height="768" alt="image" src="https://github.com/user-attachments/assets/c6e02f9f-2384-4fe5-b87b-0bce7455a2b0" />


DS18B20s use the 1-Wire protocol, so several sensors can share the same data pin (and a single 4.7kΩ pull-up resistor). Each sensor has a unique 64-bit ROM address and appears as its own `28-xxxx` device under `/sys/bus/w1/devices/`.

The app discovers every sensor on the bus automatically:

- `temp.list_sensors()` — IDs of all connected sensors
- `temp.read_temp(device_id=None)` — read one sensor (defaults to the first)
- `temp.read_all()` — read every sensor, returning `{device_id: temperature_c}`

Each reading is stored in InfluxDB tagged with its `sensor_id`, and the web dashboard renders a separate readout + chart card per sensor.

## Hot plate control

`temp_control.py` closes the loop: it drives an SSR (via GPIO17 → 1 kΩ → 2N2222A low-side switch) using DS18B20 readings as feedback, with a PID loop and time-proportioned SSR switching. The controller runs in a background thread, so the web dashboard and data logging stay live during a run.

From the dashboard: enter a target temperature (and an optional hold duration in minutes) in the **Hot Plate Control** panel and press Start. The panel shows the state (heating/holding), current duty cycle, and hold progress; Stop turns the heater off immediately.

API:

- `POST /api/control/start` with `{"target_c": 60, "minutes": 10}` (`minutes` optional — omit to hold until stopped)
- `POST /api/control/stop`
- `GET /api/control/status`

While a run is active, setpoint and duty are logged alongside the sensor readings (CSV rows `setpoint` / `duty`, InfluxDB measurement `control`).

From the command line or Python:

```bash
python temp_control.py 60 10   # hold 60 °C for 10 minutes, then shut off
```

Safety rails: hard 110 °C ceiling (DS18B20 max is 125 °C), heat-up timeout, sensor-stall detection, and the SSR is forced off on any exit, error, or Ctrl-C. Keep the plate's own thermostat in series as a hardware backstop and fuse the AC hot side — SSRs fail shorted.

Requires `gpiozero` with the `lgpio` backend (`RPi.GPIO` does not work on the Pi 5). The venv uses the system `lgpio` package via `include-system-site-packages = true`.

**Acknowledgements**

Built the circuit and the code with the help of raspberry pi tutorial:
https://www.circuitbasics.com/raspberry-pi-ds18b20-temperature-sensor-tutorial/

Claude Code CLI:
Claude Opus 4.8
