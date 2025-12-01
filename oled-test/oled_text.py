from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import sh1106
from PIL import ImageFont
import time

serial = i2c(port=1, address=0x3C)
device = sh1106(serial)

with canvas(device) as draw:
  draw.text((0,0), "Hello, OLED!", fill="white")


time.sleep(10)
