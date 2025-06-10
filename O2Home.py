#!/usr/bin/env python3
import sys
import time
import threading
import os

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

            if strength > 0:
                # map for 180° rotation
                fx = DISPLAY_W - raw_x
                fy = DISPLAY_H - raw_y
                idx = hit(fx,fy)

                # on press change
                if idx != last_btn:
                    draw_buttons(active=idx)
                    last_btn = idx
                    if idx == 0:
                        press_time = time.time()
                    else:
                        press_time = None

                # if still holding button 0, check duration
                if idx == 0 and press_time:
                    if time.time() - press_time >= 1.0:
                        # replace this process with RunO2.py
                        _cleanup_and_exec()
                # for button 1, nothing further to do
            else:
                # on release
                if last_btn is not None:
                    draw_buttons(active=None)
                    last_btn = None
                    press_time = None

            time.sleep(0.02)

    finally:
        global _irq_run
        _irq_run = False
        epd.sleep()

def _cleanup_and_exec():
    """Stop IRQ thread and exec RunO2.py in place of this script."""
    global _irq_run
    _irq_run = False
    # small delay to let EPD finish drawing
    time.sleep(0.1)
    # exec the new script, replacing this process
    os.execvp("python3", ["python3", "RunO2.py"])

if __name__ == "__main__":
    main()
