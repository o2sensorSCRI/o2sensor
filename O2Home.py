import os
import time
import threading
from PIL import Image, ImageDraw, ImageFont
from waveshare_epd import epd2in13_V3 as epd_driver

# Touch support
from evdev import InputDevice, ecodes, list_devices

# ==========================
# CONFIGURATION
# ==========================
TOUCH_DEVICE = '/dev/input/event0'  # Change if needed for your system

# ==========================
# Display constants
# ==========================
epd = epd_driver.EPD()
epd.init(epd.FULL_UPDATE)
epd.Clear(0xFF)
display_w, display_h = epd.width, epd.height     # 250×122
land_w, land_h = display_h, display_w           # 122×250

# ==========================
# Fonts
# ==========================
font_btn = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)

# ==========================
# Button layout (landscape mode)
# ==========================
BUTTONS = [
    {
        'label': "Start O2 sensor",
        'bbox': (10, 50, land_w//2 - 10, land_h - 50), # (x0, y0, x1, y1)
        'color': 0,
        'callback': lambda: os.system("python3 RunO2.py")
    },
    {
        'label': "Update software/settings",
        'bbox': (land_w//2 + 10, 50, land_w - 10, land_h - 50),
        'color': 0,
        'callback': lambda: os.system("python3 Update.py")
    }
]

# ==========================
# Draw main GUI
# ==========================
def draw_gui():
    img = Image.new("1", (land_w, land_h), 255)
    draw = ImageDraw.Draw(img)
    # Optional: Title
    title = "O2 Sensor Menu"
    bbox_title = draw.textbbox((0,0), title, font=font_title)
    title_w = bbox_title[2] - bbox_title[0]
    draw.text(((land_w-title_w)//2, 10), title, font=font_title, fill=0)

    # Draw buttons
    for btn in BUTTONS:
        x0, y0, x1, y1 = btn['bbox']
        draw.rectangle(btn['bbox'], fill=btn['color'], outline=0, width=2)
        # Center label
        bbox = draw.textbbox((0,0), btn['label'], font=font_btn)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        label_x = x0 + (x1-x0-w)//2
        label_y = y0 + (y1-y0-h)//2
        draw.text((label_x, label_y), btn['label'], font=font_btn, fill=255)
    # Rotate for landscape
    buf = epd.getbuffer(img.rotate(-90, expand=True))
    epd.display(buf)

# ==========================
# Touch processing
# ==========================
def get_touch_device():
    devices = [InputDevice(path) for path in list_devices()]
    for d in devices:
        if "touch" in d.name.lower() or "ft5406" in d.name.lower():
            return d
    # fallback
    return InputDevice(TOUCH_DEVICE)

def run_touch_loop():
    dev = get_touch_device()
    print(f"Using touch device: {dev.path}")
    abs_x = abs_y = None
    for event in dev.read_loop():
        if event.type == ecodes.EV_ABS:
            if event.code == ecodes.ABS_X:
                abs_x = event.value
            elif event.code == ecodes.ABS_Y:
                abs_y = event.value
        elif event.type == ecodes.EV_KEY and event.code == ecodes.BTN_TOUCH and event.value == 0:  # Touch release
            # Map raw abs_x, abs_y to display coords
            if abs_x is None or abs_y is None:
                continue
            # Touchscreen calibration
            # For FT5406 on Pi, ABS_X in [0, 4095] -> y on screen; ABS_Y in [0, 4095] -> x on screen (rotated)
            # Map to landscape
            touch_x = int(abs_y / 4095 * land_w)
            touch_y = int((4095 - abs_x) / 4095 * land_h)
            # Hit test buttons
            for btn in BUTTONS:
                x0, y0, x1, y1 = btn['bbox']
                if x0 <= touch_x <= x1 and y0 <= touch_y <= y1:
                    print(f"Button '{btn['label']}' pressed")
                    threading.Thread(target=btn['callback']).start()
                    break

# ==========================
# MAIN
# ==========================
if __name__ == "__main__":
    draw_gui()
    touch_thread = threading.Thread(target=run_touch_loop, daemon=True)
    touch_thread.start()
    while True:
        time.sleep(1)
