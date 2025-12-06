from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import sh1106
from PIL import Image
import time

serial = i2c(port=1, address=0x3C)
device = sh1106(serial)

with canvas(device) as draw:
  image = Image.open("stick.jpg")
  # Convert to grayscale, resize to display size, then convert to 1-bit
  image = image.convert("L")  # Convert to grayscale
  image = image.resize((128, 64))  # Resize to display dimensions
  image = image.convert("1")  # Convert to 1-bit monochrome
  draw.bitmap((0,0), image, fill="white")


time.sleep(10)
