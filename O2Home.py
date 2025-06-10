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
    { "label": "Start O2 sensor",
      "rect": (MARGIN, MARGIN,
               MARGIN + BUTTON_W, MARGIN + BUTTON_H) },
    { "label": "Update software/settings",
      "rect": (MARGIN, 2*MARGIN + BUTTON_H,
               MARGIN + BUTTON_W, 2*MARGIN + 2*BUTTON_H) },
]

font = ImageFont.truetype(
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 14)

# ─── Init EPD & Touch ────────────────────────────────────────────────────────────
epd    = EPD()
gt     = GT1151()
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
    d   = ImageDraw.Draw(img)
    for i,b in enumerate(BUTTONS):
        x0,y0,x1,y1 = b["rect"]
        if i == active:
            d.rectangle((x0,y0,x1,y1), fill=0, outline=0)
            col = 255
        else:
            d.rectangle((x0,y0,x1,y1), fill=255, outline=0)
            col = 0
        bb = d.textbbox((0,0), b["label"], font=font)
        w,h = bb[2]-bb[0], bb[3]-bb[1]
        tx = x0 + ((x1-x0)-w)//2
        ty = y0 + ((y1-y0)-h)//2
        d.text((tx,ty), b["label"], font=font, fill=col)
    buf = epd.getbuffer(img.rotate(180))
    epd.init(epd.FULL_UPDATE)
    epd.display(buf)
    epd.init(epd.PART_UPDATE)

# ─── Message Screen ──────────────────────────────────────────────────────────────
def show_message(message, duration=3):
    img = Image.new("1", (DISPLAY_W, DISPLAY_H), 255)
    d   = ImageDraw.Draw(img)
    bb = d.textbbox((0,0), message, font=font)
    w,h = bb[2]-bb[0], bb[3]-bb[1]
    x = (DISPLAY_W - w) // 2
    y = (DISPLAY_H - h) // 2
    d.text((x,y), message, font=font, fill=0)
    buf = epd.getbuffer(img.rotate(180))
    epd.init(epd.FULL_UPDATE)
    epd.display(buf)
    time.sleep(duration)
    epd.init(epd.PART_UPDATE)

# ─── Hit test ───────────────────────────────────────────────────────────────────
def hit(x,y):
    for i,b in enumerate(BUTTONS):
        x0,y0,x1,y1 = b["rect"]
        if x0 <= x <= x1 and y0 <= y <= y1:
            return i
    return None

# ─── Main Loop ──────────────────────────────────────────────────────────────────
def main():
    draw_buttons(active=None)
    last_btn = None
    press_time = None

    try:
        while True:
            gt.GT_Scan(GT_Dev, GT_Old)
            raw_x, raw_y, strength = GT_Dev.X[0], GT_Dev.Y[0], GT_Dev.S[0]
            fx = DISPLAY_W - raw_x
            fy = DISPLAY_H - raw_y

            if strength > 0:
                idx = hit(fx,fy)
                if idx != last_btn:
                    draw_buttons(active=idx)
                    last_btn = idx
                    press_time = time.time()
                else:
                    # still pressing same button
                    if press_time and (time.time() - press_time) >= 2.0:
                        if idx == 0:
                            # Launch RunO2.py and quit GUI
                            _cleanup_and_exec(os.path.expanduser('~/o2sensor/RunO2.py'))
                        elif idx == 1:
                            # Run Update.py and show message
                            subprocess.run(['python3', os.path.expanduser('~/o2sensor/Update.py')])
                            show_message("Software/settings updated", duration=3)
                            draw_buttons(active=None)
                            last_btn = None
                            press_time = None
            else:
                if last_btn is not None:
                    draw_buttons(active=None)
                    last_btn = None
                    press_time = None

            time.sleep(0.02)

    finally:
        global _irq_run
        _irq_run = False
        epd.sleep()


def _cleanup_and_exec(script_path):
    global _irq_run
    _irq_run = False
    time.sleep(0.1)
    os.execvp('python3', ['python3', script_path])

if __name__ == "__main__":
    main()
