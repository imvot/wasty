#!/usr/bin/which python3
from adafruit_servokit import ServoKit
import time

kit = ServoKit(channels=16)
servo = kit.servo[0]
servo.set_pulse_width_range(500, 2500)
motor = kit.continuous_servo[1]

CENTER = 97.5
LEFT = CENTER + 30
RIGHT = CENTER - 30
servo.angle = CENTER
motor.throttle = 0.0
time.sleep(2)


motor.throttle = 0.4
time.sleep(3)
servo.angle = LEFT
time.sleep(1)
servo.angle = RIGHT
time.sleep(1)

motor.throttle = 0.0
servo.angle = CENTER

