import board
import busio
import adafruit_ssd1306
import time

i2c = busio.I2C(board.SCL, board.SDA)
oled = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c, addr=0x3C)

while True:
    oled.fill(0)
    # Clear screen
    oled.text('OLED IS WORKING',0, 0, 1)
    oled.text('Address: 0x3C', 0, 15, 1)
    oled.text('Raspberry Pi', 0, 30, 1)
    oled.show()
    oled.sleep(2)

    oled.fill(1)
    oled.show()
    time.sleep(1)
