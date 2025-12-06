# python3 -m venv venv --system-site-packages
# source venv/bin/activate
# pip install -r requirements.txt

import RPi.GPIO as GPIO
import time

BUTTON_PIN = 17
counter = 0

GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
last_state = GPIO.input(BUTTON_PIN)

print(f"Monitoring GPIO pin {BUTTON_PIN}. Press Ctrl+C to stop.")

try:
    while True:
        current_state = GPIO.input(BUTTON_PIN)
        if current_state == GPIO.LOW and last_state == GPIO.HIGH:
            counter += 1
            print(f"Button pressed! Count: {counter}")
            time.sleep(0.3)  # Debounce delay
        last_state = current_state
        time.sleep(0.01)  # Small delay to prevent CPU spinning
except KeyboardInterrupt:
    print(f"\nTotal button presses: {counter}")
finally:
    GPIO.cleanup()
