#!/usr/bin/env python3
"""
Shows currently pressed keys from an input device once per second.
Reads directly from /dev/input/eventX via evdev — bypasses pygame/SDL
entirely, so it works over SSH with no local console session.
"""
import evdev
from evdev import InputDevice, categorize, ecodes
import threading
import time

# --- List devices and pick the keyboard ---
devices = [InputDevice(path) for path in evdev.list_devices()]
if not devices:
    print("No input devices found. Check permissions (see notes below).")
    raise SystemExit(1)

print("Available input devices:")
for i, dev in enumerate(devices):
    print(f"  {i}: {dev.path} - {dev.name}")

idx = int(input("\nSelect your Bluetooth keyboard's index: "))
keyboard = devices[idx]
print(f"\nListening on: {keyboard.name} ({keyboard.path})")
print("Press Ctrl+C to stop.\n")

# --- Background thread tracks live key state ---
pressed_keys = set()
lock = threading.Lock()

def event_listener():
    for event in keyboard.read_loop():
        if event.type == ecodes.EV_KEY:
            key_event = categorize(event)
            with lock:
                if key_event.keystate == key_event.key_down:
                    pressed_keys.add(key_event.keycode)
                elif key_event.keystate == key_event.key_up:
                    pressed_keys.discard(key_event.keycode)

threading.Thread(target=event_listener, daemon=True).start()

# --- Print snapshot every second ---
try:
    while True:
        with lock:
            snapshot = set(pressed_keys)
        label = snapshot if snapshot else "(none)"
        print(f"[{time.strftime('%H:%M:%S')}] Pressed: {label}")
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopped.")
