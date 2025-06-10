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
MARGIN_OUT = 5
SPACING = 10
BUTTON_W = (DISPLAY_W - 2 * MARGIN_OUT - SPACING) // 2
BUTTON_H = DISPLAY_H - 2 * MARGIN_OUT

# Side-by-side button rectangles
BUTTONS = [
    {
        "label": "Start O2 sensor",
        "rect": (
            MARGIN_OUT,
            MARGIN_OUT,
            MARGIN_OUT + BUTTON_W,
            MARGIN_OUT + BUTTON_H
        )
    },
    {
        "label": "Update software/settings",
        "rect": (
            MARGIN_OUT + BUTTON_W + SPACING,
            MARGIN_OUT,
            MARGIN_OUT + 2 * BUTTON_W + SPACING,
            MARGIN_OUT + BUTTON_H
        )
    }
]

font = ImageFont.truetype(
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 14
)

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
        fill = 0 if i == active else 255
        d.rectangle((x0, y0, x1, y1), fill=fill, outline=0)
        col = 255 if i == active else 0
        # center text, shrink if needed
        label = b["label"]
        bbox = d.textbbox((0, 0), label, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        font_use = font
        if w > BUTTON_W - 10:
            font_use = ImageFont.truetype(
                '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 12
            )
            bbox = d.textbbox((0, 0), label, font=font_use)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = x0 + (BUTTON_W - w) // 2
        ty = y0 + (BUTTON_H - h) // 2
        d.text((tx, ty), label, font=font_use, fill=col)
    buf = epd.getbuffer(img.rotate(180))
    epd.displayPartial(buf)

# ─── Hit test ───────────────────────────────────────────────────────────────────
def hit(x, y):
    for i, b in enumerate(BUTTONS):
        x0, y0, x1, y1 = b["rect"]
        if x0 <= x <= x1 and y0 <= y <= y1:
            return i
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
                idx = hit(fx, fy)
                if idx != last_btn:
                    # new touch
                    last_btn = idx
                    press_start = time.time() if idx is not None else None
                    fill_changed = False
                elif idx is not None and not fill_changed:
                    # check hold
                    if press_start and (time.time() - press_start) >= 2.0:
                        draw_buttons(active=idx)
                        fill_changed = True
                        press_start = time.time()
                elif fill_changed and (time.time() - press_start) >= 1.0:
                    # trigger action
                    if last_btn == 0:
                        os.execvp('python3', ['python3', os.path.expanduser('~/O2_Sensor/RunO2.py')])
                    else:
                        # show updating...
                        img = Image.new("1", (DISPLAY_W, DISPLAY_H), 255)
                        d = ImageDraw.Draw(img)
                        msg = "Updating..."
                        bb = d.textbbox((0, 0), msg, font=font)
                        w_u, h_u = bb[2] - bb[0], bb[3] - bb[1]
                        d.text(
                            ((DISPLAY_W - w_u) // 2, (DISPLAY_H - h_u) // 2),
                            msg, font=font, fill=0
                        )
                        epd.displayPartial(epd.getbuffer(img.rotate(180)))
                        subprocess.run([
                            'python3',
                            os.path.expanduser('~/O2_Sensor/Update.py')
                        ], check=True)
                        # confirmation
                        img = Image.new("1", (DISPLAY_W, DISPLAY_H), 255)
                        d = ImageDraw.Draw(img)
                        msg2 = "Software/settings updated"
                        bb2 = d.textbbox((0, 0), msg2, font=font)
                        w2, h2 = bb2[2] - bb2[0], bb2[3] - bb2[1]
                        d.text(
                            ((DISPLAY_W - w2) // 2, (DISPLAY_H - h2) // 2),
                            msg2, font=font, fill=0
                        )
                        epd.displayPartial(epd.getbuffer(img.rotate(180)))
                        time.sleep(3)
                        draw_buttons(active=None)
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
