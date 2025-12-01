import board
import busio
from digitalio import DigitalInOut
from adafruit_pn532.i2c import PN532_I2C
import RPi.GPIO as GPIO
import time

LED_PIN = 17  # GPIO pin connected to LED

# Initialize I2C communication
i2c = busio.I2C(board.SCL, board.SDA)
pn532 = PN532_I2C(i2c, debug=False)

GPIO.setmode(GPIO.BCM)  # Use BCM GPIO numbering
GPIO.setup(LED_PIN, GPIO.OUT)  # Set pin as output

# Get firmware version
ic, ver, rev, support = pn532.firmware_version
print(f"Found PN532 with firmware version: {ver}.{rev}")

# Configure PN532 to read RFID/NFC tags
pn532.SAM_configuration()

# Clear data before writing
def clear_tag_data(start_block, num_blocks):
    empty_data = b'\x00\x00\x00\x00'  # 4 bytes of zeros
    print("Clearing tag data...")
    for block in range(start_block, start_block + num_blocks):
        try:
            print(f"Clearing block {block}")
            pn532.ntag2xx_write_block(block, empty_data)
        except Exception as e:
            print(f"Error clearing block {block}: {e}")
            break

data_to_write = "Atan"  # 16 bytes
# Convert string to bytes
data_bytes = data_to_write.encode('ascii')

# Ensure data is padded to a multiple of 4 bytes
if len(data_bytes) % 4 != 0:
    padding = 4 - (len(data_bytes) % 4)
    data_bytes = data_bytes + (b'\x00' * padding)

print("Waiting for an NFC tag...")

while True:
    uid = pn532.read_passive_target(timeout=0.5)
    if uid:
        print(f"Found NFC card with UID: {uid.hex().upper()}")
        GPIO.output(LED_PIN, GPIO.HIGH)
        time.sleep(1)

        # Clear data first (starting from block 4, clearing several blocks)
        num_blocks_to_clear = (len(data_bytes) + 3) // 4  # Calculate how many blocks we need
        clear_tag_data(4, num_blocks_to_clear)

        # Write in 4-byte chunks
        for i in range(0, len(data_bytes), 4):
            block_number = 4 + (i // 4)  # Start at block 4, increment every 4 bytes
            chunk = data_bytes[i:i+4]
            print(f"Writing to block {block_number}: {chunk}")
            pn532.ntag2xx_write_block(block_number, chunk)

        print("Write successful! Remove the NFC tag.")
        # Wait until tag is removed
        while pn532.read_passive_target(timeout=0.5):
            time.sleep(0.1)
            
        print("\nWaiting for next NFC tag...")
        GPIO.output(LED_PIN, GPIO.LOW)

    time.sleep(0.1)