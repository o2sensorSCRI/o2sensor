#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import time
from PIL import Image, ImageDraw, ImageFont

# --- adjust these paths as needed ---
libdir = os.path.join(os.path.dirname(__file__), 'lib')
if os.path.isdir(libdir):
    sys.path.append(libdir)

from TP_lib import epd2in13_V3

def load_button_font(size):
    # 1) Try the common DejaVuSans on Raspbian
    dejavu = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    try:
        return ImageFont.truetype(dejavu, size)
    except OSError:
        print(f"Warning: could not load {dejavu}, falling back to default font")
        return ImageFont.load_default()

def main():
    # initialize display (full refresh to clear)
    epd = epd2in13_V3.EPD()
    epd.init(epd.FULL_UPDATE)
    epd.Clear(0xFF)

    # create a white canvas
    W, H = 250, 122
    image = Image.new('1', (W, H), 255)
    draw = ImageDraw.Draw(image)

    # define square button centered
    side = 80
    x0 = (W - side) // 2
    y0 = (H - side) // 2
    x1, y1 = x0 + side, y0 + side

    # draw black square
    draw.rectangle([(x0, y0), (x1, y1)], fill=0)

    # load font (size ~24)
    font = load_button_font(24)

    # compute text position
    text = "B1"
    tw, th = draw.textsize(text, font=font)
    tx = x0 + (side - tw) // 2
    ty = y0 + (side - th) // 2

    # draw "B1" in white
    draw.text((tx, ty), text, font=font, fill=255)

    # partial refresh
    epd.init(epd.PART_UPDATE)
    epd.displayPartial(epd.getbuffer(image))

    time.sleep(2)
    epd.sleep()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit()
