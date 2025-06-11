#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import time
from PIL import Image, ImageDraw, ImageFont

# modify these paths if your project layout is different
picdir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'pic/2in13')
fontdir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'pic')

# insert the library path if necessary
libdir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'lib')
if os.path.exists(libdir):
    sys.path.append(libdir)

from TP_lib import epd2in13_V3

def main():
    # 1) Initialize the display
    epd = epd2in13_V3.EPD()
    epd.init(epd.FULL_UPDATE)
    # clear to white
    epd.Clear(0xFF)

    # 2) Create a blank image -- white background
    # according to the manual: resolution is 250×122 pixels :contentReference[oaicite:0]{index=0}
    width, height = 250, 122
    image = Image.new('1', (width, height), 255)  # 255: clear white

    draw = ImageDraw.Draw(image)

    # 3) Define our square button
    # choose a side length (e.g. 80 pixels)
    side = 80
    x0 = (width - side) // 2
    y0 = (height - side) // 2
    x1 = x0 + side
    y1 = y0 + side

    # draw filled rectangle (0 = black)
    draw.rectangle([ (x0, y0), (x1, y1) ], fill=0)

    # 4) Draw the label "B1" in the center of the button
    # load a TrueType font at size 24 (adjust path/name as needed)
    font_path = os.path.join(fontdir, 'Font.ttc')
    font = ImageFont.truetype(font_path, 24)

    text = "B1"
    tw, th = draw.textsize(text, font=font)
    tx = x0 + (side - tw) // 2
    ty = y0 + (side - th) // 2

    # 255 = white
    draw.text((tx, ty), text, font=font, fill=255)

    # 5) Send the image buffer to the display with a partial update
    epd.init(epd.PART_UPDATE)
    epd.displayPartial(epd.getbuffer(image))

    # 6) Sleep when done
    time.sleep(2)
    epd.sleep()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
