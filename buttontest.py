#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import time
from PIL import Image, ImageDraw, ImageFont

# === adjust paths to match your project ===
libdir = os.path.join(os.path.dirname(__file__), 'lib')
if os.path.isdir(libdir):
    sys.path.append(libdir)

from TP_lib import epd2in13_V3
import xpt2046  # Waveshare touch controller driver

# display size
W, H = 250, 122

# button definition (before rotation)
SIDE = 80
BX0 = (W - SIDE) // 2
BY0 = (H - SIDE) // 2
BX1 = BX0 + SIDE
BY1 = BY0 + SIDE

def load_button_font(size):
    path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        print(f"Warning: could not load {path}, using default font")
        return ImageFont.load_default()

def draw_button(img, inverted=False):
    """Draw the button onto a PIL image, inverted if requested."""
    draw = ImageDraw.Draw(img)
    if inverted:
        draw.rectangle([(BX0, BY0), (BX1, BY1)], fill=255)  # white box
        fill_text, fill_box = 0, 255
    else:
        draw.rectangle([(BX0, BY0), (BX1, BY1)], fill=0)    # black box
        fill_text, fill_box = 255, 0

    font = load_button_font(24)
    text = "B1"
    try:
        tw, th = font.getsize(text)
    except AttributeError:
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        tw, th = (r - l), (b - t)

    tx = BX0 + (SIDE - tw) // 2
    ty = BY0 + (SIDE - th) // 2
    draw.text((tx, ty), text, font=font, fill=fill_text)

def map_touch(x, y):
    """Map raw touch coords (0..W,0..H) through 180° rotation."""
    return (W - x, H - y)

def main():
    # 1) Init display & clear with a full update
    epd = epd2in13_V3.EPD()
    epd.init(epd.FULL_UPDATE)
    epd.Clear(0xFF)

    # 2) Prepare initial image (white background)
    base = Image.new('1', (W, H), 255)
    draw_button(base, inverted=False)

    # rotate 180° for display
    disp_img = base.rotate(180)

    # 3) Show it with a partial update
    epd.init(epd.PART_UPDATE)
    epd.displayPartial(epd.getbuffer(disp_img))

    # 4) Set up touch
    touch = xpt2046.XPT2046()  # adjust init args if needed

    inverted = False
    print("Waiting for touch in button area…")

    while True:
        if touch.touched():
            x_raw, y_raw = touch.read()
            # wait for release
            while touch.touched():
                time.sleep(0.01)
            # map through rotation
            x, y = map_touch(x_raw, y_raw)
            # check if release was inside the button (pre-rotation coords)
            if BX0 <= x <= BX1 and BY0 <= y <= BY1:
                inverted = not inverted
                # redraw base and re-rotate
                base = Image.new('1', (W, H), 255)
                draw_button(base, inverted=inverted)
                disp_img = base.rotate(180)
                epd.displayPartial(epd.getbuffer(disp_img))
                print(f"Button {'inverted' if inverted else 'normal'}")
        time.sleep(0.05)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Exiting…")
        sys.exit()
