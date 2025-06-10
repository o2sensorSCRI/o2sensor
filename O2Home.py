#!/usr/bin/env python3
import sys
import time
import threading
import os
import subprocess

from TP_lib.gt1151 import GT1151, GT_Development
from TP_lib.epd2in13_V3 import EPD
from PIL import Image, ImageDraw, ImageFont

# ─── Configuration ───────────────────────────────────────────────────────────────
DISPLAY_W, DISPLAY_H = 250, 122
MARGIN_OUT = 5
SPACING    = 10
BUTTON_W   = (DISPLAY_W - 2*MARGIN_OUT - SPACING) // 2
BUTTON_H   = DISPLAY_H - 2*MARGIN_OUT

BUTTONS = [
    {
        "label_lines": ["Start", "O2 sensor"],
        "rect": (MARGIN_OUT,
                 MARGIN_OUT,
                 MARGIN_OUT + BUTTON_W,
                 MARGIN_OUT + BUTTON_H)
    },
    {
        "label_lines": ["Update", "software", "and", "settings"],
        "rect": (MARGIN_OUT + BUTTON_W + SPACING,
                 MARGIN_OUT,
                 MARGIN_OUT + 2*BUTTON_W + SPACING,
                 MARGIN_OUT + BUTTON_H)
    }
]

BASE_FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
font      = ImageFont.truetype(BASE_FONT, 14)

# ─── Initialize EPD & Touch ─────────────────────────────────────────────────────
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
    draw = ImageDraw.Draw(img)
    for i, btn in enumerate(BUTTONS):
        x0, y0, x1, y1 = btn["rect"]
        fill = 0 if i == active else 255
        draw.rectangle((x0, y0, x1, y1), fill=fill, outline=0)
        color = 255 if i == active else 0

        # multi-line centered text
        lines = btn["label_lines"]
        heights, widths = [], []
        for line in lines:
            bb = draw.textbbox((0,0), line, font=font)
            widths.append(bb[2]-bb[0])
            heights.append(bb[3]-bb[1])
        total_h = sum(heights) + (len(lines)-1)*3
        y_text = y0 + (BUTTON_H - total_h)//2
        for line, w, h in zip(lines, widths, heights):
            x_text = x0 + (BUTTON_W - w)//2
            draw.text((x_text, y_text), line, font=font, fill=color)
            y_text += h + 3

    buf = epd.getbuffer(img.rotate(180))
    epd.displayPartial(buf)

# ─── Hit Test ───────────────────────────────────────────────────────────────────
def hit(x, y):
    for i, btn in enumerate(BUTTONS):
        x0, y0, x1, y1 = btn["rect"]
        if x0 <= x <= x1 and y0 <= y <= y1:
            return i
    return None

# ─── Main Loop ──────────────────────────────────────────────────────────────────
def main():
    draw_buttons(active=None)
    last_btn    = None
    press_start = None
    fill_changed= False

    try:
        while True:
            gt.GT_Scan(GT_Dev, GT_Old)
            raw_x, raw_y, strength = GT_Dev.X[0], GT_Dev.Y[0], GT_Dev.S[0]
            fx = DISPLAY_W - raw_x
            fy = DISPLAY_H - raw_y

            if strength > 0:
                idx = hit(fx, fy)
                if idx != last_btn:
                    # new touch
                    print(f"Touched button {idx}")
                    last_btn    = idx
                    press_start = time.time() if idx is not None else None
                    fill_changed= False
                    draw_buttons(active=None)
                elif idx is not None and not fill_changed and (time.time() - press_start) >= 1.0:
                    # 1 sec hold → change fill/text
                    print(f"Button {idx} held 1s → highlight")
                    draw_buttons(active=idx)
                    fill_changed = True
                    press_start  = time.time()
                elif fill_changed and (time.time() - press_start) >= 0.5:
                    # 0.5 s after highlight → trigger action
                    if idx == 0:
                        print("Launching RunO2.py…")
                        os.execvp('python3',
                                  ['python3', os.path.expanduser('~/O2_Sensor/RunO2.py')])
                    else:
                        print("Launching Update.py…")
                        # “Updating…” message
                        img = Image.new("1", (DISPLAY_W, DISPLAY_H), 255)
                        d   = ImageDraw.Draw(img)
                        msg = "Updating..."
                        bb  = d.textbbox((0,0), msg, font=font)
                        d.text(((DISPLAY_W - (bb[2]-bb[0]))//2,
                                (DISPLAY_H - (bb[3]-bb[1]))//2),
                               msg, font=font, fill=0)
                        epd.displayPartial(epd.getbuffer(img.rotate(180)))

                        # Run Update.py in correct cwd to avoid permissions
                        subprocess.run(
                            ['python3', os.path.expanduser('~/O2_Sensor/Update.py')],
                            cwd=os.path.expanduser('~/O2_Sensor'),
                            check=True
                        )

                        print("Update.py finished successfully")
                        # confirmation on screen
                        img = Image.new("1", (DISPLAY_W, DISPLAY_H), 255)
                        d   = ImageDraw.Draw(img)
                        msg2 = "Software/settings updated"
                        bb2  = d.textbbox((0,0), msg2, font=font)
                        d.text(((DISPLAY_W - (bb2[2]-bb2[0]))//2,
                                (DISPLAY_H - (bb2[3]-bb2[1]))//2),
                               msg2, font=font, fill=0)
                        epd.displayPartial(epd.getbuffer(img.rotate(180)))
                        time.sleep(2)
                        draw_buttons(active=None)
                    # done action; wait for release
                    last_btn = None
            else:
                if last_btn is not None and not fill_changed:
                    draw_buttons(active=None)
                last_btn = None
                press_start = None
                fill_changed= False

            time.sleep(0.02)
    finally:
        global _irq_run
        _irq_run = False
        epd.sleep()

if __name__ == "__main__":
    main()
