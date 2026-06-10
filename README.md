# pi5_ds18b20_demo
Temperature monitoring application for one or more DS18B20 sensors. Features a live graph of observed temperatures over a period of 10 minutes.
<img width="882" height="660" alt="temp_monitor" src="https://github.com/user-attachments/assets/cf0dce22-0f66-459d-9a94-fe3ec3a81425" />

## Multiple sensors

DS18B20s use the 1-Wire protocol, so several sensors can share the same data pin (and a single 4.7kΩ pull-up resistor). Each sensor has a unique 64-bit ROM address and appears as its own `28-xxxx` device under `/sys/bus/w1/devices/`.

The app discovers every sensor on the bus automatically:

- `temp.list_sensors()` — IDs of all connected sensors
- `temp.read_temp(device_id=None)` — read one sensor (defaults to the first)
- `temp.read_all()` — read every sensor, returning `{device_id: temperature_c}`

Each reading is stored in InfluxDB tagged with its `sensor_id`, and the web dashboard renders a separate readout + chart card per sensor.


**Acknowledgements**

Built the circuit and the code with the help of raspberry pi tutorial:
https://www.circuitbasics.com/raspberry-pi-ds18b20-temperature-sensor-tutorial/

Local LLM also helped write some of the code:
qwen3.6-35b-a3b
