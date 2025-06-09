import sys
import os
import time

from TP_lib.gt1151 import GT1151, GT_Development
from TP_lib.epd2in13_V3 import EPD
from PIL import Image, ImageDraw, ImageFont

font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'  # Adjust if necessary

# EPD and Touch Init
epd = EPD()
gt = GT1151()
GT_Dev = GT_Development()
GT_Old = GT_Development()
epd.init(epd.FULL_UPDATE)
gt.GT_Init()
epd.Clear(0xFF)

# GUI Layout: Landscape (250x122), buttons stacked vertically
DISPLAY_W, DISPLAY_H = 250, 122
BUTTON_W = DISPLAY_W - 40  # 20 px left/right margin
BUTTON_H = (DISPLAY_H - 3 * 20) // 2  # 2 buttons, 20 px vertical margin between and around

# First button top left corner
BUTTON1_X = 20
BUTTON1_Y = 20
# Second button below
BUTTON2_X = 20
BUTTON2_Y = BUTTON1_Y + BUTTON_H + 20

BUTTONS = [
    {
        "label": "Start O2 sensor",
        "rect": (BUTTON1_X, BUTTON1_Y, BUTTON1_X + BUTTON_W, BUTTON1_Y + BUTTON_H)
    },
    {
        "label": "Update software/settings",
        "rect": (BUTTON2_X, BUTTON2_Y, BUTTON2_X + BUTTON_W, BUTTON2_Y + BUTTON_H)
    }
]

font_btn = ImageFont.truetype(font_path, 18)

def wrap_text(text, font, max_width, draw):
    """Splits text into lines so each line fits inside max_width."""
    words = text.split()
    lines = []
    while words:
        line = ''
        while words:
            test_line = (line + ' ' + words[0]).strip()
            bbox = draw.textbbox((0, 0), test_line, font=font)
            w = bbox[2] - bbox[0]
            if w <= max_width:
                line = test_line
                words.pop(0)
            else:
                break
        if not line:  # Handle words that are longer than max_width
            line = words.pop(0)
        lines.append(line)
    return lines

def draw_buttons(active_idx=None, full_refresh=False):
    img = Image.new("1", (DISPLAY_W, DISPLAY_H), 255)
    draw = ImageDraw.Draw(img)
    for i, btn in enumerate(BUTTONS):
        x0, y0, x1, y1 = btn["rect"]
        box_w = x1 - x0
        box_h = y1 - y0
        # Draw button background
        if i == active_idx:
            draw.rectangle([x0, y0, x1, y1], fill=0, outline=0, width=2)
            txt_color = 255
        else:
            draw.rectangle([x0, y0, x1, y1], fill=255, outline=0, width=2)
            txt_color = 0

        # Draw text, wrapped if needed
        lines = wrap_text(btn["label"], font_btn, box_w - 10, draw)
        # Calculate total text height using textbbox for each line
        total_text_height = 0
        line_heights = []
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font_btn)
            h = bbox[3] - bbox[1]
            line_heights.append(h)
            total_text_height += h
        total_text_height += (len(lines) - 1) * 3  # line spacing

        y_text = y0 + (box_h - total_text_height) // 2
        for idx, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font_btn)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            x_text = x0 + (box_w - w) // 2
            draw.text((x_text, y_text), line, font=font_btn, fill=txt_color)
            y_text += h + 3

    buf = epd.getbuffer(img)
    if full_refresh:
        epd.init(epd.FULL_UPDATE)
        epd.display(buf)
        epd.init(epd.PART_UPDATE)
    else:
        epd.displayPartial(buf)

def get_button_idx(x, y):
    for i, btn in enumerate(BUTTONS):
        x0, y0, x1, y1 = btn["rect"]
        if x0 <= x <= x1 and y0 <= y <= y1:
            return i
    return None

def main_loop():
    draw_buttons(full_refresh=True)
    while True:
        gt.GT_Scan(GT_Dev, GT_Old)
        if (GT_Old.X[0] == GT_Dev.X[0] and
            GT_Old.Y[0] == GT_Dev.Y[0] and
            GT_Old.S[0] == GT_Dev.S[0]):
            time.sleep(0.01)
            continue

        if GT_Dev.TouchpointFlag:
            GT_Dev.TouchpointFlag = 0
            x, y = GT_Dev.X[0], GT_Dev.Y[0]
            btn_idx = get_button_idx(x, y)
            if btn_idx is not None:
                draw_buttons(active_idx=btn_idx)
                time.sleep(0.2)
                draw_buttons()
            else:
                draw_buttons()
        else:
            draw_buttons()
        time.sleep(0.05)

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        epd.sleep()
        sys.exit(0)
