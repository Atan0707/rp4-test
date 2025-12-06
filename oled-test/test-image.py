from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import sh1106
from PIL import Image
import time

serial = i2c(port=1, address=0x3C)
device = sh1106(serial)

# Open the GIF
# gif = Image.open("Ignisoul.gif")
# gif = Image.open("Ignisoul-home.gif")
gif = Image.open("Ignisoul-home-7.gif")

# Get display dimensions
display_width = 128
display_height = 64

# Function to prepare a frame for display
def prepare_frame(frame):
    # Convert to RGB first (handle all modes)
    if frame.mode == 'RGBA':
        # Handle transparency with black background
        background = Image.new('RGB', frame.size, (0, 0, 0))
        background.paste(frame, mask=frame.split()[3])
        frame = background
    elif frame.mode == 'P':
        # Palette mode - convert to RGBA then RGB
        frame = frame.convert('RGBA')
        background = Image.new('RGB', frame.size, (0, 0, 0))
        background.paste(frame, mask=frame.split()[3])
        frame = background
    elif frame.mode != 'RGB':
        # Any other mode, convert to RGB
        frame = frame.convert('RGB')
    
    # Ensure correct size
    if frame.size != (display_width, display_height):
        frame = frame.resize((display_width, display_height))
    
    # Convert to grayscale then to 1-bit (simple conversion, no dithering)
    frame = frame.convert("L").convert("1")
    
    return frame

# Animation loop
try:
    while True:
        # Reset to first frame
        gif.seek(0)
        
        # Play through all frames
        try:
            while True:
                # Prepare the current frame
                frame = prepare_frame(gif.copy())
                
                # Display the frame
                with canvas(device) as draw:
                    draw.bitmap((0, 0), frame, fill="white")
                
                # Use GIF's frame duration if available, otherwise default to 0.1s
                frame_duration = gif.info.get('duration', 100) / 1000.0  # Convert ms to seconds
                time.sleep(frame_duration)
                
                # Move to next frame
                gif.seek(gif.tell() + 1)
        except EOFError:
            # End of animation, loop will restart
            pass

except KeyboardInterrupt:
    # Clear display on exit
    with canvas(device) as draw:
        draw.rectangle((0, 0, display_width, display_height), fill="black")
