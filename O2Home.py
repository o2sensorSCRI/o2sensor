#!/usr/bin/env python3
import sys
import os
import time
import threading

from TP_lib.gt1151 import GT1151, GT_Development
from TP_lib.epd2in13_V3 import EPD
from PIL import Image, ImageDraw, ImageFont

# ─── Configuration ─────────────────────────────────────────────────────────────
font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'  # adjust if needed

DISPLAY_W, DISPLAY_H = 250, 122       # e-Paper dimensions (landscape)
MARGIN = 10
BUTTON_W = DISPLAY_W - 2 * MARGIN
BUTTON_H = (DISPLAY_H - 3 * MARGIN) // 2

BUTTONS = [
    { "label": "Start O2 sensor",
      "rect": (MARGIN, MARGIN,
               MARGIN + BUTTON_W, MARGIN + BUTTON_H) },
    { "label": "Update software/settings",
      "rect": (MARGIN, 2*MARGIN + BUTTON_H,
               MARGIN + BUTTON_W, 2*MARGIN + 2*BUTTON_H) },
]

font_btn = ImageFont.truetype(font_path, 14)  # ~30% smaller

# ─── Initialize EPD & Touch ───────────────────────────────────────────────────
epd = EPD()
gt  = GT1151()
GT_Dev = GT_Development()
GT_Old = GT_Development()

epd.init(epd.FULL_UPDATE)
gt.GT_Init()
epd.Clear(0xFF)
epd.init(epd.PART_UPDATE)

# A flag to stop the IRQ thread on exit
_irq_running = True

def touch_irq():
    """
    Background thread. Monitors the GT1151 INT pin and sets GT_Dev.Touch.
    Mirrors the Waveshare demo's pthread_irq.
    """
    while _irq_running:
        level = gt.digital_read(gt.INT)
        # level == 0 means touch detected
        GT_Dev.Touch = 1 if level == 0 else 0
        time.sleep(0.005)

# Start IRQ thread
threading.Thread(target=touch_irq, daemon=True).start()

# ─── Drawing & Utility ─────────────────────────────────────────────────────────
def draw_buttons(active_idx=None, full_refresh=False):
    img = Image.new("1", (DISPLAY_W, DISPLAY_H), 255)
    draw = ImageDraw.Draw(img)

    for i, btn in enumerate(BUTTONS):
        x0, y0, x1, y1 = btn["rect"]
        # fill & outline
        if i == active_idx:
            draw.rectangle((x0, y0, x1, y1), fill=0, outline=0, width=2)
            color = 255
        else:
            draw.rectangle((x0, y0, x1, y1), fill=255, outline=0, width=2)
            color = 0
        # center text
        bbox = draw.textbbox((0,0), btn["label"], font=font_btn)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        tx = x0 + ( (x1-x0) - w )//2
        ty = y0 + ( (y1-y0) - h )//2
        draw.text((tx,ty), btn["label"], font=font_btn, fill=color)

    # rotate 180°
    img = img.rotate(180)
    buf = epd.getbuffer(img)

    if full_refresh:
        epd.init(epd.FULL_UPDATE)
        epd.display(buf)
        epd.init(epd.PART_UPDATE)
    else:
        epd.displayPartial(buf)

def get_button_idx(x, y):
    for i, btn in enumerate(BUTTONS):
        x0,y0,x1,y1 = btn["rect"]
        if x0 <= x <= x1 and y0 <= y <= y1:
            return i
    return None

# ─── Main Loop ─────────────────────────────────────────────────────────────────
def main():
    draw_buttons(full_refresh=True)
    active = None

    try:
        while True:
            # Read touch state
            gt.GT_Scan(GT_Dev, GT_Old)
            raw_x, raw_y, strength = GT_Dev.X[0], GT_Dev.Y[0], GT_Dev.S[0]
            touched = GT_Dev.Touch

            # compute rotated coords
            fx = DISPLAY_W - raw_x
            fy = DISPLAY_H - raw_y

            # print every scan
            print(f"RAW: ({raw_x:3d},{raw_y:3d},S={strength})  ROT: ({fx:3d},{fy:3d}), Touch={touched}")

            if touched:
                idx = get_button_idx(fx, fy)
                if idx != active:
                    draw_buttons(active_idx=idx)
                    active = idx
            else:
                if active is not None:
                    draw_buttons(active_idx=None)
                    active = None

            time.sleep(0.05)

    except KeyboardInterrupt:
        pass
    finally:
        # stop IRQ thread and sleep display
        global _irq_running
        _irq_running = False
        epd.sleep()

if __name__ == "__main__":
    main()
