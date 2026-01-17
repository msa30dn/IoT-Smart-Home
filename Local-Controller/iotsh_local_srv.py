#!/usr/bin/env python3
"""
Author: Hung S. Nguyen
Date: 2026


This script runs on the local server (WSL Ubuntu) and acts as the “brain” of the
limited-scope MSE IoT project:

  Sensor ESP32  --->  MQTT  --->  This Python Controller  --->  MQTT  --->  Actuator ESP32
      (inside/outside temps)                              (relay + fan control)

It consumes temperature snapshots from the sensor node, applies a thermostat-like
control policy, and publishes actuator commands for an ESP32 that drives:
  - AC power relay (relay: 0/1)
  - Ventilation fan (fan: 0/1)

This version intentionally focuses only on Sensors + Actuators:
  - No health checks / heartbeat / LWT handling here (by design for simplicity)
  - Manual override is handled on the actuator via Blynk.Edgent (out of scope here)

MQTT Contract (Locked Interface)

1) Sensor -> Brain (combined snapshot)
   Topic: home/room1/temperature
   Retain: false
   Payload:
   {
     "device_id": "esp32_sensor_01",
     "interval_s": 10,
     "unit": "C",
     "ts": 1736881010,
     "temperatures": {
       "inside":  { "sensor_id": "temp_inside_1",  "value": 26.1 },
       "outside": { "sensor_id": "temp_outside_1", "value": 22.0 }
     }
   }

2) Brain -> Actuator (control command)
   Topic: home/room1/actuator/cmd
   Retain: false
   Payload:
   {
     "cmd_id": 1042,
     "source": "brain_wsl",
     "mode_request": "auto",
     "relay": 0|1,
     "fan": 0|1,
     "manual_for_s": 0,
     "ts": 1736882000,
     "reason": "...",
     "t_inside": 26.1,   # debug context (optional)
     "t_outside": 22.0   # debug context (optional)
   }

Actuator Output Semantics. The controller operates in 4 "desired states" which map to actuator outputs:
  desired="idle"  -> relay=0, fan=0   (AC OFF, Fan OFF)
  desired="fan"   -> relay=0, fan=1   (AC OFF, Fan ON)
  desired="ac"    -> relay=1, fan=0   (AC ON,  Fan OFF)
  desired="all"   -> relay=1, fan=1   (AC ON,  Fan ON)

Control Policy. Goal: keep indoor temperature comfortable and stable with minimal device wear.
Core rules:
  - Hysteresis band (prevents rapid toggling near the threshold):
      * Turn ON cooling/ventilation only when inside >= ON_THRESHOLD_C
      * Turn OFF (idle) only when inside <= OFF_THRESHOLD_C
      Example:
        ON_THRESHOLD_C  = 26.0
        OFF_THRESHOLD_C = 25.7  (if HYSTERESIS_C=0.3)

  - Baseline “ON” selection when inside >= ON_THRESHOLD_C:
      * If inside is "very hot" (>= ON_THRESHOLD_C + ALL_DELTA_C) -> "all"
      * Else if outside <= OUTSIDE_COOL_C -> "fan" (ventilation preferred)
      * Else -> "ac"

Escalation rules (time-based):
  - If fan has run for FAN_GRACE_S and still >= ON threshold -> switch to "ac"
  - If ac has run for AC_GRACE_S and still >= ON threshold -> switch to "all"
    BUT only if outside < inside (fan can actually help remove heat)

Anti-short-cycling rule (minimum runtime):
  - Once the controller turns ON a non-idle state (fan/ac/all),
    it will not allow a transition back to "idle" until MIN_ON_RUNTIME_S
    seconds have elapsed.
  - Transitions between ON states (fan <-> ac <-> all) are still allowed.


Dependencies
------------
- Python 3.10+
- paho-mqtt: pip install paho-mqtt

"""


from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import paho.mqtt.client as mqtt


# MQTT config
MQTT_HOST = "localhost"
MQTT_PORT = 1888

TOPIC_TEMP = "home/room1/temperature"
TOPIC_CMD = "home/room1/actuator/cmd"


# Policy config
# Hysteresis thresholds:
# - Turn ON only when inside >= ON_THRESHOLD_C
# - Turn OFF only when inside <= OFF_THRESHOLD_C
ON_THRESHOLD_C = 26.0
HYSTERESIS_C = 0.3
OFF_THRESHOLD_C = ON_THRESHOLD_C - HYSTERESIS_C  # e.g. 25.7C

OUTSIDE_COOL_C = 22.0

# Escalation timers
FAN_GRACE_S = 5 * 60          # fan -> ac escalation
AC_GRACE_S = 7 * 60           # ac -> all escalation (if outside < inside)

# "Really hot" -> all (immediate)
ALL_DELTA_C = 1.5             # inside >= ON_THRESHOLD_C + ALL_DELTA_C -> all

# Anti-short-cycling: minimum ON runtime before allowing OFF
MIN_ON_RUNTIME_S = 60

DECISION_MIN_INTERVAL_S = 3.0

# Allow relay=1 and fan=1 ("all")
FORBID_BOTH_ON = False


# State
@dataclass
class Snapshot:
    inside_c: float
    outside_c: float
    ts: int
    interval_s: Optional[int] = None
    device_id: Optional[str] = None


@dataclass
class ControllerState:
    active: str = "idle"          # "idle" | "fan" | "ac" | "all"
    since_ts: float = 0.0         # when current active state started (for escalation + min runtime)
    last_cmd_ts: float = 0.0
    cmd_id: int = 0

    # last published actuator signals
    last_cmd_relay: Optional[int] = None
    last_cmd_fan: Optional[int] = None


class IoTSmartHomeLocalController:
    def __init__(self) -> None:
        self.state = ControllerState()
        self.last_snapshot: Optional[Snapshot] = None

    #  MQTT callbacks 
    def on_connect(self, client: mqtt.Client, userdata, flags, reason_code, properties=None):
        print("Connected to MQTT, reason_code:", reason_code)
        client.subscribe(TOPIC_TEMP)

    def on_message(self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage):
        if msg.topic != TOPIC_TEMP:
            return

        try:
            snap = self.parse_snapshot(msg.payload)
        except Exception as e:
            print(f"[WARN] Bad sensor snapshot: {e}")
            return

        self.last_snapshot = snap
        self.evaluate_and_publish(client, snap)

    #  Parsing 
    @staticmethod
    def parse_snapshot(payload_bytes: bytes) -> Snapshot:
        raw = payload_bytes.decode("utf-8", errors="replace").strip()
        obj = json.loads(raw)

        temps = obj["temperatures"]
        inside_c = float(temps["inside"]["value"])
        outside_c = float(temps["outside"]["value"])

        ts = int(obj.get("ts", int(time.time())))
        interval_s = obj.get("interval_s")
        device_id = obj.get("device_id")

        return Snapshot(
            inside_c=inside_c,
            outside_c=outside_c,
            ts=ts,
            interval_s=int(interval_s) if interval_s is not None else None,
            device_id=device_id,
        )

    #  Decision 
    def decide(self, snap: Snapshot) -> Tuple[str, str]:
        """
        Returns (desired_state, reason)
          desired_state in {"idle","fan","ac","all"}
        """
        t_in = snap.inside_c
        t_out = snap.outside_c
        now = time.time()

        # Helper: how long we've been in current active state
        in_state_for_s = now - self.state.since_ts if self.state.since_ts > 0 else 0.0

        # 0) Anti-short-cycling: once ON, don't allow transition to IDLE until min runtime elapsed
        #    (We still allow transitions BETWEEN on-states for safety/performance.)
        if self.state.active != "idle" and in_state_for_s < MIN_ON_RUNTIME_S:
            # If temperature is low enough to suggest turning off, we ignore it for now.
            if t_in <= OFF_THRESHOLD_C:
                return self.state.active, f"min_runtime_hold ({in_state_for_s:.0f}s<{MIN_ON_RUNTIME_S}s)"

        # 1) Hysteresis: hold idle until ON threshold; hold ON until OFF threshold
        if self.state.active == "idle":
            if t_in < ON_THRESHOLD_C:
                return "idle", "hysteresis_idle_hold (inside<on_threshold)"
        else:
            if t_in <= OFF_THRESHOLD_C:
                return "idle", "hysteresis_off (inside<=off_threshold)"

        # 2) Escalation ladder (time-based, only meaningful when ON)
        if self.state.active == "fan":
            if in_state_for_s >= FAN_GRACE_S and t_in >= ON_THRESHOLD_C:
                return "ac", "fan_timeout_escalate_to_ac"

        if self.state.active == "ac":
            if in_state_for_s >= AC_GRACE_S and t_in >= ON_THRESHOLD_C:
                if t_out < t_in:
                    return "all", "ac_timeout_escalate_to_all_outside_cooler"
                else:
                    return "ac", "ac_timeout_no_all_outside_not_cooler"

        # 3) Baseline decision (when we are considered ON)
        if t_in >= (ON_THRESHOLD_C + ALL_DELTA_C):
            return "all", "inside_high_above_threshold -> all"

        if t_in >= ON_THRESHOLD_C:
            if t_out <= OUTSIDE_COOL_C:
                return "fan", "inside>=on_threshold and outside_cool -> prefer_fan"
            else:
                return "ac", "inside>=on_threshold and outside_not_cool -> use_ac"

        # Defensive fallback
        return "idle", "fallback_idle"

    #  Mapping 
    @staticmethod
    def desired_to_outputs(desired: str) -> Tuple[int, int]:
        """
        Map desired state to actuator outputs: (relay, fan)
          idle: relay=0, fan=0
          fan:  relay=0, fan=1
          ac:   relay=1, fan=0
          all:  relay=1, fan=1
        """
        if desired == "idle":
            return 0, 0
        if desired == "fan":
            return 0, 1
        if desired == "ac":
            return 1, 0
        if desired == "all":
            return 1, 1
        raise ValueError(f"Unknown desired state: {desired}")

    #  Publishing 
    def publish_cmd(self, client: mqtt.Client, desired: str, reason: str, snap: Snapshot):
        relay, fan = self.desired_to_outputs(desired)

        if FORBID_BOTH_ON and relay == 1 and fan == 1:
            raise ValueError("Invalid output: relay=1 and fan=1 (forbidden by policy)")

        self.state.cmd_id += 1
        now_ts = int(time.time())

        cmd = {
            "cmd_id": self.state.cmd_id,
            "source": "brain_wsl",
            "mode_request": "auto",
            "relay": relay,
            "fan": fan,
            "manual_for_s": 0,
            "ts": now_ts,
            "reason": reason,
            "t_inside": snap.inside_c,
            "t_outside": snap.outside_c,
        }

        payload = json.dumps(cmd)
        client.publish(TOPIC_CMD, payload, qos=0, retain=False)

        # Update trackers
        prev = self.state.active
        self.state.active = desired
        self.state.since_ts = time.time()
        self.state.last_cmd_ts = time.time()
        self.state.last_cmd_relay = relay
        self.state.last_cmd_fan = fan

        print(
            f"[CMD] {prev} -> {desired} | relay={relay} fan={fan} | "
            f"inside={snap.inside_c:.2f} outside={snap.outside_c:.2f} | "
            f"cmd_id={self.state.cmd_id} | {reason}"
        )

    def evaluate_and_publish(self, client: mqtt.Client, snap: Snapshot):
        desired, reason = self.decide(snap)

        # Rate limiting
        now = time.time()
        if (now - self.state.last_cmd_ts) < DECISION_MIN_INTERVAL_S:
            return

        relay, fan = self.desired_to_outputs(desired)

        # Skip if outputs unchanged
        same_as_last = (
            self.state.last_cmd_relay is not None
            and self.state.last_cmd_fan is not None
            and relay == self.state.last_cmd_relay
            and fan == self.state.last_cmd_fan
        )

        if same_as_last:
            print(
                f"[SKIP] outputs unchanged (relay={relay}, fan={fan}) | "
                f"desired={desired} | inside={snap.inside_c:.2f} outside={snap.outside_c:.2f} | {reason}"
            )
            return

        self.publish_cmd(client, desired, reason, snap)


def main():
    controller = IoTSmartHomeLocalController()

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = controller.on_connect
    client.on_message = controller.on_message

    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)

    print("IoTSmartHomeLocalController running.")
    print(f"  Subscribed: {TOPIC_TEMP}")
    print(f"  Publishing: {TOPIC_CMD}")
    print(
        f"  ON_THRESHOLD_C={ON_THRESHOLD_C}, OFF_THRESHOLD_C={OFF_THRESHOLD_C} (HYSTERESIS_C={HYSTERESIS_C})\n"
        f"  MIN_ON_RUNTIME_S={MIN_ON_RUNTIME_S}s\n"
        f"  OUTSIDE_COOL_C={OUTSIDE_COOL_C}, FAN_GRACE_S={FAN_GRACE_S}s, AC_GRACE_S={AC_GRACE_S}s, ALL_DELTA_C={ALL_DELTA_C}"
    )

    client.loop_forever()


if __name__ == "__main__":
    main()
