#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import time
from PIL import Image, ImageDraw, ImageFont

# adjust if your library dir is elsewhere
libdir = os.path.join(os.path.dirname(__file__), 'lib')
if os.path.isdir(libdir):
    sys.path.append(libdir)
from TP_lib import epd2in13_V3

def load_button_font(size):
    dejavu = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    try:
        return ImageFont.truetype(dejavu, size)
    except OSError:
        print(f"Warning: could not load {dejavu}, using default font")
        return ImageFont.load_default()

def main():
    # 1) Init & clear
    epd = epd2in13_V3.EPD()
    epd.init(epd.FULL_UPDATE)
    epd.Clear(0xFF)

    # 2) New canvas
    W, H = 250, 122
    image = Image.new('1', (W, H), 255)
    draw  = ImageDraw.Draw(image)

    # 3) Button coords
    side = 80
    x0 = (W - side) // 2
    y0 = (H - side) // 2
    x1, y1 = x0 + side, y0 + side

    draw.rectangle([(x0, y0), (x1, y1)], fill=0)

    # 4) Text size: try font.getsize(), else textbbox()
    font = load_button_font(24)
    text = "B1"
    try:
        tw, th = font.getsize(text)
    except AttributeError:
        # newer Pillow: get a tight bounding box
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        tw, th = r - l, b - t

    tx = x0 + (side - tw) // 2
    ty = y0 + (side - th) // 2
    draw.text((tx, ty), text, font=font, fill=255)

    # 5) Partial refresh
    epd.init(epd.PART_UPDATE)
    epd.displayPartial(epd.getbuffer(image))

    time.sleep(2)
    epd.sleep()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit()
