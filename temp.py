import os
import glob
import time
 
os.system('modprobe w1-gpio')
os.system('modprobe w1-therm')
 
base_dir = '/sys/bus/w1/devices/'

def list_sensors():
    """Return the IDs of every DS18B20 on the bus, e.g. ['28-0000abc', ...]."""
    return sorted(os.path.basename(f) for f in glob.glob(base_dir + '28*'))

def read_temp_raw(device_id):
    with open(base_dir + device_id + '/w1_slave', 'r') as f:
        return f.readlines()

def read_temp(device_id=None):
    """Read one sensor in Celsius. Defaults to the first sensor on the bus."""
    if device_id is None:
        sensors = list_sensors()
        if not sensors:
            raise RuntimeError('No DS18B20 sensors found on the bus')
        device_id = sensors[0]
    lines = read_temp_raw(device_id)
    while lines[0].strip()[-3:] != 'YES':
        time.sleep(0.2)
        lines = read_temp_raw(device_id)
    equals_pos = lines[1].find('t=')
    if equals_pos != -1:
        temp_string = lines[1][equals_pos+2:]
        temp_c = float(temp_string) / 1000.0
        return temp_c

def read_all():
    """Read every sensor on the bus. Returns {device_id: temp_c}."""
    return {sid: read_temp(sid) for sid in list_sensors()}