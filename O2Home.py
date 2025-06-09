import sys
import os
import time
import threading

# --- Waveshare EPD and Touch drivers ---
from TP_lib import gt1151
from TP_lib import epd2in13_V3
from PIL import Image, ImageDraw, ImageFont

# --- Paths for font, etc. ---
font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'  # or use your font path

# --- Screen/EPD Init ---
epd = epd2in13_V3.EPD()
gt = gt1151.GT1151()
GT_Dev = gt1151.GT_Development()
GT_Old = gt1151.GT_Development()
epd.init(epd.FULL_UPDATE)
gt.GT_Init()
epd.Clear(0xFF)
epd.init(epd.PART_UPDATE)

# --- Button Layout (landscape mode, [X0, Y0, X1, Y1]) ---
BUTTONS = [
    {
        "label": "Start O2 sensor",
        "rect": (16, 36, 106, 76),
        "callback": lambda: os.system("python3 RunO2.py"),
        "active": False
    },
    {
        "label": "Update software/settings",
        "rect": (16, 86, 106, 126),
        "callback": lambda: os.system("python3 Update.py"),
        "active": False
    }
]
# (x0, y0, x1, y1) => buttons 90x40, spaced for a 122x250 landscape area

# --- Font ---
font_btn = ImageFont.truetype(font_path, 16)

def draw_buttons(active_idx=None):
    """Draws buttons, active_idx (0 or 1) is filled black with white text."""
    W, H = 122, 250  # landscape dimensions
    img = Image.new("1", (W, H), 0)  # background black for the menu style
    draw = ImageDraw.Draw(img)
    for i, btn in enumerate(BUTTONS):
        x0, y0, x1, y1 = btn["rect"]
        if i == active_idx:
            # Active: filled black
            draw.rectangle([x0, y0, x1, y1], fill=0, outline=255, width=2)
            # Center text
            bbox = draw.textbbox((0, 0), btn["label"], font=font_btn)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(
                (x0 + (x1 - x0 - w)//2, y0 + (y1 - y0 - h)//2),
                btn["label"], font=font_btn, fill=255
            )
        else:
            # Normal: white fill, black border
            draw.rectangle([x0, y0, x1, y1], fill=255, outline=0, width=2)
            bbox = draw.textbbox((0, 0), btn["label"], font=font_btn)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(
                (x0 + (x1 - x0 - w)//2, y0 + (y1 - y0 - h)//2),
                btn["label"], font=font_btn, fill=0
            )
    buf = epd.getbuffer(img.rotate(-90, expand=True))
    epd.displayPartial(buf)

# --- Touch handler logic ---
def get_button_idx(x, y):
    # Returns index of pressed button or None
    for i, btn in enumerate(BUTTONS):
        x0, y0, x1, y1 = btn["rect"]
        if x0 <= x <= x1 and y0 <= y <= y1:
            return i
    return None

def main_loop():
    last_pressed = None
    draw_buttons()
    while True:
        gt.GT_Scan(GT_Dev, GT_Old)
        # Only register if touch actually moved/changed
        if (GT_Old.X[0] == GT_Dev.X[0] and
            GT_Old.Y[0] == GT_Dev.Y[0] and
            GT_Old.S[0] == GT_Dev.S[0]):
            time.sleep(0.01)
            continue

        if GT_Dev.TouchpointFlag:
            GT_Dev.TouchpointFlag = 0
            x, y = GT_Dev.X[0], GT_Dev.Y[0]
            btn_idx = get_button_idx(x, y)
            if btn_idx is not None:
                draw_buttons(active_idx=btn_idx)
                last_pressed = btn_idx
                # Visual feedback for a short press
                time.sleep(0.2)
                draw_buttons()
                # Trigger the action
                BUTTONS[btn_idx]["callback"]()
            else:
                draw_buttons()
        else:
            draw_buttons()
        time.sleep(0.05)

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        epd.sleep()
        sys.exit(0)
