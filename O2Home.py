import sys
import os
import time
import threading

# Import custom driver libraries
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'TP_lib'))
from gt1151 import GT1151, GT_Development
from epd2in13_V3 import EPD
from PIL import Image, ImageDraw, ImageFont

font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'  # Adjust if necessary

# EPD and Touch Init
epd = EPD()
gt = GT1151()
GT_Dev = GT_Development()
GT_Old = GT_Development()
epd.init(epd.FULL_UPDATE)
gt.GT_Init()
epd.Clear(0xFF)

# GUI Layout: Landscape (250x122)
DISPLAY_W, DISPLAY_H = 250, 122
BUTTON_W = (DISPLAY_W - 3 * 20) // 2  # two buttons, 20px margins
BUTTON_H = 60
BUTTON_Y = (DISPLAY_H - BUTTON_H) // 2
LEFT_X = 20
RIGHT_X = LEFT_X + BUTTON_W + 20

BUTTONS = [
    {
        "label": "Start O2 sensor",
        "rect": (LEFT_X, BUTTON_Y, LEFT_X + BUTTON_W, BUTTON_Y + BUTTON_H),
        "callback": lambda: os.system("python3 RunO2.py"),
        "active": False
    },
    {
        "label": "Update software/settings",
        "rect": (RIGHT_X, BUTTON_Y, RIGHT_X + BUTTON_W, BUTTON_Y + BUTTON_H),
        "callback": lambda: os.system("python3 Update.py"),
        "active": False
    }
]

font_btn = ImageFont.truetype(font_path, 18)

def draw_buttons(active_idx=None, full_refresh=False):
    """Draws side-by-side buttons, does full refresh if needed."""
    img = Image.new("1", (DISPLAY_W, DISPLAY_H), 255)
    draw = ImageDraw.Draw(img)
    for i, btn in enumerate(BUTTONS):
        x0, y0, x1, y1 = btn["rect"]
        if i == active_idx:
            draw.rectangle([x0, y0, x1, y1], fill=0, outline=0, width=2)
            bbox = draw.textbbox((0, 0), btn["label"], font=font_btn)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(
                (x0 + (x1 - x0 - w)//2, y0 + (y1 - y0 - h)//2),
                btn["label"], font=font_btn, fill=255
            )
        else:
            draw.rectangle([x0, y0, x1, y1], fill=255, outline=0, width=2)
            bbox = draw.textbbox((0, 0), btn["label"], font=font_btn)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(
                (x0 + (x1 - x0 - w)//2, y0 + (y1 - y0 - h)//2),
                btn["label"], font=font_btn, fill=0
            )
    buf = epd.getbuffer(img)
    if full_refresh:
        epd.init(epd.FULL_UPDATE)
        epd.display(buf)
        epd.init(epd.PART_UPDATE)
    else:
        epd.displayPartial(buf)

def get_button_idx(x, y):
    for i, btn in enumerate(BUTTONS):
        x0, y0, x1, y1 = btn["rect"]
        if x0 <= x <= x1 and y0 <= y <= y1:
            return i
    return None

def main_loop():
    last_pressed = None
    draw_buttons(full_refresh=True)
    while True:
        gt.GT_Scan(GT_Dev, GT_Old)
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
                time.sleep(0.2)
                draw_buttons()
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
