"""
temp_control.py — Hot plate temperature control for thermochromic label testing.

Drives an SSR through a GPIO -> 1 k -> 2N2222A low-side switch (SSR Input-
switched to GND, Input+ on the 5 V PSU, grounds commoned). Temperature
feedback comes from the DS18B20 bus via temp.py.

The controller runs in a background thread so the Flask interface
(interface.py) and its data logging keep working during a run.

Requires gpiozero + lgpio (RPi.GPIO does not work on the Pi 5's RP1 chip).

CLI use:
    python temp_control.py 60 10     # hold 60 degC for 10 minutes, then off

Library use:
    from temp_control import controller
    controller.start(60, minutes=10)   # minutes=None -> hold until stop()
    controller.status()
    controller.stop()
"""

import threading
import time
import atexit

import temp  # DS18B20 access, shared with interface.py

from gpiozero import DigitalOutputDevice

# ---------------------------------------------------------------- settings
HEAT_PIN = 17            # BCM pin driving the transistor base (via 1 k)
CONTROL_SENSOR_ID = None  # 1-Wire ID to control on, None = first on the bus
MAX_TEMP_C = 110.0       # hard safety limit — DS18B20 absolute max is 125 degC
MAX_HEAT_MINUTES = 90    # give up if target not reached in this time
WINDOW_S = 2.0           # time-proportioning window for the SSR
SETTLE_BAND_C = 1.0      # "at temperature" means within +/- this band
SENSOR_STALL_S = 15      # abort if no fresh reading for this long
SENSOR_READ_TIMEOUT_S = 2.0  # bound each wait for a valid DS18B20 CRC

# Conservative starting PID gains for a small hot plate. Tune if needed:
# raise KP if approach is too slow, lower it if overshoot is large.
KP, KI, KD = 0.08, 0.002, 0.4


class PID:
    def __init__(self, kp, ki, kd, out_min=0.0, out_max=1.0):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.out_min, self.out_max = out_min, out_max
        self.integral = 0.0
        self.prev_err = None
        self.prev_t = None

    def update(self, setpoint, measured):
        now = time.monotonic()
        err = setpoint - measured
        dt = 0.0 if self.prev_t is None else now - self.prev_t
        d = 0.0
        if dt > 0 and self.prev_err is not None:
            self.integral += err * dt
            # Anti-windup: clamp the integral to the range that maps to a
            # reachable output. The heater can only add heat (out_min == 0), so
            # a negative integral is physically meaningless -- and dangerous: it
            # winds down while the SSR sits forced-off above the band, then pins
            # the output at zero long after the temperature has fallen back
            # below target, so the heater never re-engages.
            if self.ki:
                self.integral = max(self.out_min / self.ki,
                                    min(self.out_max / self.ki, self.integral))
            else:
                self.integral = 0.0
            d = (err - self.prev_err) / dt
        self.prev_err, self.prev_t = err, now
        out = self.kp * err + self.ki * self.integral + self.kd * d
        return max(self.out_min, min(self.out_max, out))


class HotPlateController:
    """Background-thread hot plate control with safety rails.

    States: idle -> heating -> holding -> done | stopped | fault
    """

    def __init__(self):
        self._heater = None
        self._thread = None
        self._stop_evt = threading.Event()
        self._lock = threading.Lock()
        self._status = {"state": "idle"}

    # ------------------------------------------------------------ hardware
    def _get_heater(self):
        if self._heater is None:
            # active_high=True, initial_value=False -> SSR off at startup
            self._heater = DigitalOutputDevice(HEAT_PIN, initial_value=False)
        return self._heater

    def heater_off(self):
        """Force the SSR off. Safe to call any time."""
        if self._heater is not None:
            self._heater.off()

    # ------------------------------------------------------------ public API
    def start(self, target_c, minutes=None):
        """Begin a control run. minutes=None holds until stop() is called."""
        target_c = float(target_c)
        if not 0 < target_c <= MAX_TEMP_C:
            raise ValueError(
                f"target must be between 0 and {MAX_TEMP_C} degC")
        if minutes is not None:
            minutes = float(minutes)
            if minutes <= 0:
                raise ValueError("minutes must be positive")
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("a control run is already active")
            self._stop_evt.clear()
            self._status = {
                "state": "heating",
                "target_c": target_c,
                "hold_minutes": minutes,
                "current_temp_c": None,
                "duty": 0.0,
                "time_to_target_s": None,
                "hold_elapsed_s": None,
                "hold_min_c": None,
                "hold_max_c": None,
                "error": None,
            }
            self._thread = threading.Thread(
                target=self._run, args=(target_c, minutes), daemon=True)
            self._thread.start()

    def stop(self):
        """Request shutdown of the active run; the SSR turns off promptly."""
        self._stop_evt.set()
        self.heater_off()

    def status(self):
        with self._lock:
            return dict(self._status)

    def is_active(self):
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------ internals
    def _update(self, **kw):
        with self._lock:
            self._status.update(kw)

    def _apply_duty(self, heater, duty):
        """Time-proportioning: SSR on for duty*WINDOW_S, off for the rest.

        Uses the stop event for the waits so stop() interrupts immediately.
        """
        on_time = duty * WINDOW_S
        if on_time > 0.05:
            heater.on()
            if self._stop_evt.wait(on_time):
                heater.off()
                return
        if WINDOW_S - on_time > 0.05:
            heater.off()
            self._stop_evt.wait(WINDOW_S - on_time)

    def _run(self, target_c, minutes):
        heater = None
        end_state = "stopped"
        try:
            # Keep initialization inside the fault boundary. Otherwise a GPIO
            # backend/permission error kills the thread while status remains
            # misleadingly stuck at "heating".
            heater = self._get_heater()
            pid = PID(KP, KI, KD)
            start = time.monotonic()
            time_to_target = None
            hold_started = None
            hold_min = hold_max = None
            last_reading_t = time.monotonic()

            while not self._stop_evt.is_set():
                # ---- read sensor, with stall detection -------------------
                try:
                    t = temp.read_temp(
                        CONTROL_SENSOR_ID, timeout_s=SENSOR_READ_TIMEOUT_S)
                    if t is None:
                        raise RuntimeError("bad reading")
                    last_reading_t = time.monotonic()
                except Exception as e:
                    if time.monotonic() - last_reading_t > SENSOR_STALL_S:
                        raise RuntimeError(f"sensor stalled: {e}")
                    heater.off()
                    self._update(duty=0.0)
                    if self._stop_evt.wait(1):
                        break
                    continue

                now = time.monotonic()

                # ---- safety rails ---------------------------------------
                if t > MAX_TEMP_C:
                    raise RuntimeError(
                        f"over-temp: {t:.1f} degC > {MAX_TEMP_C} degC limit")
                if hold_started is None and now - start > MAX_HEAT_MINUTES * 60:
                    raise RuntimeError("timeout: never reached target")

                # ---- state machine --------------------------------------
                at_temp = abs(t - target_c) <= SETTLE_BAND_C
                if time_to_target is None and at_temp:
                    time_to_target = now - start
                if hold_started is None and time_to_target is not None:
                    hold_started = now
                if hold_started is not None:
                    hold_min = t if hold_min is None else min(hold_min, t)
                    hold_max = t if hold_max is None else max(hold_max, t)
                    if minutes is not None and now - hold_started >= minutes * 60:
                        end_state = "done"
                        break

                # ---- drive heater ---------------------------------------
                duty = pid.update(target_c, t)
                if t > target_c + SETTLE_BAND_C:
                    duty = 0.0  # cooling is passive; don't fight physics

                self._update(
                    state="holding" if hold_started is not None else "heating",
                    current_temp_c=t,
                    duty=round(duty, 3),
                    time_to_target_s=time_to_target,
                    hold_elapsed_s=(now - hold_started
                                    if hold_started is not None else None),
                    hold_min_c=hold_min,
                    hold_max_c=hold_max,
                )
                self._apply_duty(heater, duty)
        except Exception as e:
            end_state = "fault"
            self._update(error=str(e))
        finally:
            if heater is not None:
                try:
                    heater.off()  # ALWAYS off on exit, error, or stop
                except Exception as e:
                    end_state = "fault"
                    previous_error = self.status().get("error")
                    off_error = f"failed to turn heater off: {e}"
                    self._update(error=(
                        f"{previous_error}; {off_error}"
                        if previous_error else off_error))
            self._update(state=end_state, duty=0.0)


controller = HotPlateController()
atexit.register(controller.stop)


def keep(target_c, minutes, poll_s=2.0, log=print):
    """Blocking convenience wrapper: reach target_c, hold `minutes`, shut off.

    Returns dict with time_to_target_s and min/max temp seen during the hold.
    """
    controller.start(target_c, minutes)
    try:
        while controller.is_active():
            s = controller.status()
            if s.get("current_temp_c") is not None:
                log(f"t={s['current_temp_c']:6.2f} degC "
                    f"target={target_c} duty={s['duty']:4.2f} [{s['state']}]")
            time.sleep(poll_s)
    finally:
        controller.stop()
    s = controller.status()
    if s["state"] == "fault":
        raise RuntimeError(s["error"])
    return {
        "time_to_target_s": s["time_to_target_s"],
        "held_minutes": minutes,
        "hold_min_c": s["hold_min_c"],
        "hold_max_c": s["hold_max_c"],
    }


if __name__ == "__main__":
    import sys
    tgt = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
    mins = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    print(keep(tgt, mins))
