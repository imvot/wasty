#!/usr/bin/env python3
"""
RC car keyboard control via evdev + Adafruit ServoKit.

Two selectable modes:

  1) held  - W/S held = throttle (0.6, boosted to 1.0 with Shift)
             Caps Lock = toggle cruise control (locks current throttle)
  2) step  - each separate W/S keystroke changes throttle by a fixed
             step; value is retained when keys are released.
             No boost, no cruise control in this mode.

Common to both modes:
  A / D        - steering left / right, released -> center
  Backspace    - toggle emergency stop (latches until pressed again)

Assumes:
  - Steering servo on kit.servo[STEERING_CHANNEL]
  - ESC/motor on kit.continuous_servo[MOTOR_CHANNEL] (.throttle in [-1.0, 1.0])
"""

import time
import threading
import evdev
from evdev import InputDevice, categorize, ecodes
from adafruit_servokit import ServoKit

# --- Config ---
STEERING_CHANNEL = 0
MOTOR_CHANNEL = 1

CENTER = 105
LEFT = CENTER + 40
RIGHT = CENTER - 35

THROTTLE_NORMAL = 0.6      # held mode
THROTTLE_BOOST = 1.0       # held mode
STEP_INCREMENT = 0.2       # step mode
THROTTLE_MIN = -1.0
THROTTLE_MAX = 1.0

LOOP_HZ = 50


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


# --- Mode selection ---
print("Select control mode:")
print("  1) Held    - W/S held = throttle, Shift = boost, Caps Lock = cruise")
print("  2) Step    - each W/S press changes throttle by a fixed step")
choice = input("Enter 1 or 2: ").strip()
MODE = "step" if choice == "2" else "held"
print(f"Mode: {MODE}\n")

# --- Hardware setup ---
kit = ServoKit(channels=16)
steering = kit.servo[STEERING_CHANNEL]
motor = kit.continuous_servo[MOTOR_CHANNEL]

print("Arming ESC (neutral for 2s)...")
motor.throttle = 0
time.sleep(2)
steering.angle = CENTER
print("Armed. Ready.\n")

# --- Keyboard device selection ---
devices = [InputDevice(path) for path in evdev.list_devices()]
print("Available input devices:")
for i, dev in enumerate(devices):
    print(f"  {i}: {dev.path} - {dev.name}")

idx = int(input("\nSelect your keyboard's index: "))
keyboard = devices[idx]
print(f"Listening on: {keyboard.name}\n")

# --- Shared state ---
pressed = set()
lock = threading.Lock()

cruise_locked = False     # held mode only
cruise_throttle = 0.0     # held mode only
step_throttle = 0.0       # step mode only
estop = False


def compute_throttle_held():
    """Throttle from current W/S/Shift state. Opposing keys = neutral."""
    w = "KEY_W" in pressed
    s = "KEY_S" in pressed
    shift = "KEY_LEFTSHIFT" in pressed or "KEY_RIGHTSHIFT" in pressed

    if w and not s:
        direction = 1
    elif s and not w:
        direction = -1
    else:
        return 0.0

    magnitude = THROTTLE_BOOST if shift else THROTTLE_NORMAL
    return direction * magnitude


def compute_throttle():
    if MODE == "held":
        return compute_throttle_held()
    else:
        return step_throttle


def compute_steering():
    """Steering angle from current A/D state. Opposing keys = center."""
    a = "KEY_A" in pressed
    d = "KEY_D" in pressed
    if a and not d:
        return LEFT
    elif d and not a:
        return RIGHT
    else:
        return CENTER


def handle_keydown(keycode):
    """Toggle/step-style keys, handled once per press edge (called under lock)."""
    global cruise_locked, cruise_throttle, step_throttle, estop

    keys = keycode if isinstance(keycode, list) else [keycode]

    # --- Step mode: each keystroke nudges throttle ---
    if MODE == "step" and not estop:
        if "KEY_W" in keys:
            step_throttle = clamp(step_throttle + STEP_INCREMENT, THROTTLE_MIN, THROTTLE_MAX)
            print(f"Throttle: {step_throttle:.2f}")
        elif "KEY_S" in keys:
            step_throttle = clamp(step_throttle - STEP_INCREMENT, THROTTLE_MIN, THROTTLE_MAX)
            print(f"Throttle: {step_throttle:.2f}")

    # --- Held mode: cruise control ---
    if MODE == "held" and "KEY_CAPSLOCK" in keys:
        if estop:
            return  # ignore cruise toggling while e-stopped
        if not cruise_locked:
            current = compute_throttle_held()
            if current == 0.0:
                print("No throttle held - nothing to lock.")
            else:
                cruise_locked = True
                cruise_throttle = current
                print(f"Cruise control ON at throttle={cruise_throttle}")
        else:
            cruise_locked = False
            print("Cruise control OFF")

    # --- Both modes: emergency stop ---
    if "KEY_BACKSPACE" in keys:
        estop = not estop
        if estop:
            if MODE == "held":
                cruise_locked = False
            else:
                step_throttle = 0.0
            print("EMERGENCY STOP engaged - press Backspace again to release")
        else:
            print("Emergency stop released")


def event_listener():
    for event in keyboard.read_loop():
        if event.type == ecodes.EV_KEY:
            ke = categorize(event)
            with lock:
                if ke.keystate == ke.key_down:
                    pressed.add(ke.keycode)
                    handle_keydown(ke.keycode)
                elif ke.keystate == ke.key_up:
                    pressed.discard(ke.keycode)


threading.Thread(target=event_listener, daemon=True).start()

# --- Control loop ---
try:
    while True:
        with lock:
            if estop:
                throttle = 0.0
            elif MODE == "held" and cruise_locked:
                throttle = cruise_throttle
            else:
                throttle = compute_throttle()
            angle = compute_steering()

        motor.throttle = throttle
        steering.angle = angle

        time.sleep(1 / LOOP_HZ)

except KeyboardInterrupt:
    print("\nShutting down - returning to neutral")
    motor.throttle = 0
    steering.angle = CENTER
