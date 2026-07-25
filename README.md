# SBC-Temperature-Controller
Temperature monitoring and control application using DS18B20 sensor. Features a live graph of observed temperatures over a period of 10 minutes.

<img width="1728" height="991" alt="Screenshot 2026-07-24 at 8 09 27 PM" src="https://github.com/user-attachments/assets/1840ed7d-7fe8-44b5-94b1-bc178263a3e5" />

## Circuit

<img width="849" height="875" alt="Screenshot 2026-07-24 at 8 48 36 PM" src="https://github.com/user-attachments/assets/e04f30b8-8fb2-4c38-bc95-395d95050a37" />

<img width="5712" height="4284" alt="circuit_photo" src="https://github.com/user-attachments/assets/c644a300-9a1a-4da9-b8ae-8dfcfaf27742" />

## Hot plate control

`temp_control.py` closes the loop: it drives an SSR (via GPIO17 → 1 kΩ → 2N2222A low-side switch) using DS18B20 readings as feedback, with a PID loop and time-proportioned SSR switching. The controller runs in a background thread, so the web dashboard and data logging stay live during a run.

From the dashboard: enter a target temperature (and an optional hold duration in minutes) in the **Hot Plate Control** panel and press Start. The panel shows the state (heating/holding), current duty cycle, and hold progress; Stop turns the heater off immediately.

API:

- `POST /api/control/start` with `{"target_c": 60, "minutes": 10}` (`minutes` optional — omit to hold until stopped)
- `POST /api/control/stop`
- `GET /api/control/status`

While a run is active, setpoint and duty are logged alongside the sensor readings (CSV rows `setpoint` / `duty`, InfluxDB measurement `control`).

**Command line and Python library usage**

CLI:

```bash
python temp_control.py 60 10   # hold 60 °C for 10 minutes, then shut off
```

Library:

    from temp_control import controller
    controller.start(60, minutes=10)   # minutes=None -> hold until stop()
    controller.status()
    controller.stop()

Safety rails: hard 110 °C ceiling (DS18B20 max is 125 °C), heat-up timeout, sensor-stall detection, and the SSR is forced off on any exit, error, or Ctrl-C. Keep the plate's own thermostat in series as a hardware backstop and fuse the AC hot side — SSRs fail shorted.

Requires `gpiozero` with the `lgpio` backend (`RPi.GPIO` does not work on the Pi 5). The venv uses the system `lgpio` package via `include-system-site-packages = true`.

## Acknowledgements

Raspberry pi tutorial:

https://www.circuitbasics.com/raspberry-pi-ds18b20-temperature-sensor-tutorial/

AI Tools:

Claude Code (Claude Opus 4.8)

Codex (GPT-5.6-Sol)
