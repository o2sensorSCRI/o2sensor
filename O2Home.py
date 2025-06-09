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

# GUI Layout: Landscape (250x122), buttons stacked vertically and bigger
DISPLAY_W, DISPLAY_H = 250, 122
MARGIN = 10
BUTTON_W = DISPLAY_W - 2 * MARGIN
BUTTON_H = (DISPLAY_H - 3 * MARGIN) // 2

BUTTONS = [
    {
        "label": "Start O2 sensor",
        "rect": (MARGIN, MARGIN, MARGIN + BUTTON_W, MARGIN + BUTTON_H)
    },
    {
        "label": "Update software/settings",
        "rect": (MARGIN, 2 * MARGIN + BUTTON_H, MARGIN + BUTTON_W, 2 * MARGIN + 2 * BUTTON_H)
    }
]

font_btn = ImageFont.truetype(font_path, 20)

def draw_buttons(active_idx=None, full_refresh=False):
    img = Image.new("1", (DISPLAY_W, DISPLAY_H), 255)
    draw = ImageDraw.Draw(img)
    for i, btn in enumerate(BUTTONS):
        x0, y0, x1, y1 = btn["rect"]
        box_w = x1 - x0
        box_h = y1 - y0

        # Draw background and set text color
        if i == active_idx:
            draw.rectangle([x0, y0, x1, y1], fill=0, outline=0, width=2)
            txt_color = 255
        else:
            draw.rectangle([x0, y0, x1, y1], fill=255, outline=0, width=2)
            txt_color = 0

        # Draw label centered (no wrapping, label fits by design)
        bbox = draw.textbbox((0, 0), btn["label"], font=font_btn)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x_text = x0 + (box_w - w) // 2
        y_text = y0 + (box_h - h) // 2
        draw.text((x_text, y_text), btn["label"], font=font_btn, fill=txt_color)

    # Flip image 180 degrees
    img = img.rotate(180)
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
    active_btn = None
    touching = False
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
            print(f"Touch: ({x}, {y})")  # Print coordinates

            btn_idx = get_button_idx(x, y)
            if btn_idx is not None and (not touching or active_btn != btn_idx):
                draw_buttons(active_idx=btn_idx)
                active_btn = btn_idx
                touching = True
            elif btn_idx is None and touching:
                draw_buttons()
                active_btn = None
                touching = False
        else:
            if touching:
                draw_buttons()
                active_btn = None
                touching = False
        time.sleep(0.05)

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        epd.sleep()
        sys.exit(0)
