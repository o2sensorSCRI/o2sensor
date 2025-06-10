#!/usr/bin/env python3
import sys
import time
import threading
import os
import subprocess

from TP_lib.gt1151 import GT1151, GT_Development
from TP_lib.epd2in13_V3 import EPD
from PIL import Image, ImageDraw, ImageFont

# ─── Config ─────────────────────────────────────────────────────────────────────
DISPLAY_W, DISPLAY_H = 250, 122
MARGIN = 10
BUTTON_W = DISPLAY_W - 2 * MARGIN
BUTTON_H = (DISPLAY_H - 3 * MARGIN) // 2

BUTTONS = [
    {"label": "Start O2 sensor",
     "rect": (MARGIN, MARGIN, MARGIN + BUTTON_W, MARGIN + BUTTON_H)},
    {"label": "Update software/settings",
     "rect": (MARGIN, 2 * MARGIN + BUTTON_H,
              MARGIN + BUTTON_W, 2 * MARGIN + 2 * BUTTON_H)},
]

font = ImageFont.truetype(
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 14)

# ─── Init EPD & Touch ────────────────────────────────────────────────────────────
epd = EPD()
gt = GT1151()
GT_Dev = GT_Development()
GT_Old = GT_Development()

epd.init(epd.FULL_UPDATE)
gt.GT_Init()
epd.Clear(0xFF)
epd.init(epd.PART_UPDATE)

_irq_run = True

def touch_irq():
    while _irq_run:
        lvl = gt.digital_read(gt.INT)
        GT_Dev.Touch = 1 if lvl == 0 else 0
        time.sleep(0.002)

threading.Thread(target=touch_irq, daemon=True).start()

# ─── Drawing ─────────────────────────────────────────────────────────────────────
def draw_buttons(active=None):
    img = Image.new("1", (DISPLAY_W, DISPLAY_H), 255)
    d = ImageDraw.Draw(img)
    for i, b in enumerate(BUTTONS):
        x0, y0, x1, y1 = b["rect"]
        if i == active:
            d.rectangle((x0, y0, x1, y1), fill=0, outline=0)
            col = 255
        else:
            d.rectangle((x0, y0, x1, y1), fill=255, outline=0)
            col = 0
        bb = d.textbbox((0, 0), b["label"], font=font)
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        tx = x0 + ((x1 - x0) - w) // 2
        ty = y0 + ((y1 - y0) - h) // 2
        d.text((tx, ty), b["label"], font=font, fill=col)
    buf = epd.getbuffer(img.rotate(180))
    epd.displayPartial(buf)

# ─── Hit test with reduced areas ─────────────────────────────────────────────────
def hit_reduced(x, y):
    # Button 0: bottom 70% only
    x0, y0, x1, y1 = BUTTONS[0]["rect"]
    height0 = y1 - y0
    threshold0 = y0 + int(0.3 * height0)
    if x0 <= x <= x1 and threshold0 <= y <= y1:
        return 0
    # Button 1: bottom 70% only
    x0, y0, x1, y1 = BUTTONS[1]["rect"]
    height1 = y1 - y0
    threshold1 = y0 + int(0.3 * height1)
    if x0 <= x <= x1 and threshold1 <= y <= y1:
        return 1
    return None

# ─── Main Loop ──────────────────────────────────────────────────────────────────
def main():
    draw_buttons(active=None)
    last_btn = None
    press_start = None
    fill_changed = False

    try:
        while True:
            gt.GT_Scan(GT_Dev, GT_Old)
            raw_x, raw_y, strength = GT_Dev.X[0], GT_Dev.Y[0], GT_Dev.S[0]
            fx = DISPLAY_W - raw_x
            fy = DISPLAY_H - raw_y

            if strength > 0:
                idx = hit_reduced(fx, fy)
                if idx != last_btn:
                    # new touch region
                    draw_buttons(active=None)
                    last_btn = idx
                    press_start = time.time() if idx is not None else None
                    fill_changed = False
                elif idx is not None and not fill_changed:
                    # check for hold
                    if time.time() - press_start >= 2.0:
                        # change fill and text
                        draw_buttons(active=idx)
                        fill_changed = True
                        # reset press_start for action delay
                        press_start = time.time()
                elif fill_changed:
                    # after fill change, wait 1s then trigger
                    if time.time() - press_start >= 1.0:
                        if idx == 0:
                            # Launch RunO2.py replacing GUI
                            os.execvp('python3', ['python3', os.path.expanduser('~/o2sensor/RunO2.py')])
                        else:
                            # Update action
                            img = Image.new("1", (DISPLAY_W, DISPLAY_H), 255)
                            d = ImageDraw.Draw(img)
                            bb = d.textbbox((0, 0), "Updating...", font=font)
                            w_u, h_u = bb[2]-bb[0], bb[3]-bb[1]
                            d.text(((DISPLAY_W-w_u)//2, (DISPLAY_H-h_u)//2), "Updating...", font=font, fill=0)
                            epd.displayPartial(epd.getbuffer(img.rotate(180)))
                            subprocess.run(['python3', os.path.expanduser('~/o2sensor/Update.py')], check=True)
                            # confirmation
                            img = Image.new("1", (DISPLAY_W, DISPLAY_H), 255)
                            d = ImageDraw.Draw(img)
                            bb = d.textbbox((0, 0), "Software/settings updated", font=font)
                            w_c, h_c = bb[2]-bb[0], bb[3]-bb[1]
                            d.text(((DISPLAY_W-w_c)//2, (DISPLAY_H-h_c)//2), "Software/settings updated", font=font, fill=0)
                            epd.displayPartial(epd.getbuffer(img.rotate(180)))
                            time.sleep(3)
                            draw_buttons(active=None)
                            # reset for continued GUI
                            last_btn = None
                            press_start = None
                            fill_changed = False
            else:
                # reset on release
                if last_btn is not None:
                    draw_buttons(active=None)
                last_btn = None
                press_start = None
                fill_changed = False

            time.sleep(0.02)
    finally:
        global _irq_run
        _irq_run = False
        epd.sleep()

if __name__ == "__main__":
    main()
