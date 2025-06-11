#!/usr/bin/env python3
import sys
import time
import threading
import os
import subprocess

from TP_lib.gt1151 import GT1151, GT_Development
from TP_lib.epd2in13_V3 import EPD
from PIL import Image, ImageDraw, ImageFont

# ─── CONFIG ──────────────────────────────────────────────────────────────────────
DISPLAY_W, DISPLAY_H = 250, 122
MARGIN, SPACING     = 5, 10
BUTTON_W            = (DISPLAY_W - 2*MARGIN - SPACING)//2
BUTTON_H            = DISPLAY_H - 2*MARGIN
HOLD_TIME           = 1.0   # seconds hold before activation

BUTTONS = [
    { "label": ["Start", "O2 sensor"],
      "rect": (MARGIN, MARGIN, MARGIN+BUTTON_W, MARGIN+BUTTON_H),
      "action": "run",    # replace GUI
      "script": "~/O2_Sensor/RunO2.py"
    },
    { "label": ["Update", "software", "and", "settings"],
      "rect": (MARGIN+BUTTON_W+SPACING, MARGIN,
               MARGIN+2*BUTTON_W+SPACING, MARGIN+BUTTON_H),
      "action": "bg",     # background
      "script": "~/O2_Sensor/Update.py"
    }
]

FONT = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 14)

# ─── INIT EPD & TOUCH ───────────────────────────────────────────────────────────
epd    = EPD()
gt     = GT1151()
GT_Dev = GT_Development()
GT_Old = GT_Development()

epd.init(epd.FULL_UPDATE)
gt.GT_Init()
epd.Clear(0xFF)
epd.init(epd.PART_UPDATE)

_irq_run = True
def irq_thread():
    while _irq_run:
        GT_Dev.Touch = 1 if gt.digital_read(gt.INT)==0 else 0
        time.sleep(0.002)
threading.Thread(target=irq_thread, daemon=True).start()

# ─── DRAWING ────────────────────────────────────────────────────────────────────
def draw_buttons(active_idx=None):
    img = Image.new("1", (DISPLAY_W, DISPLAY_H), 255)
    d   = ImageDraw.Draw(img)
    for i,btn in enumerate(BUTTONS):
        x0,y0,x1,y1 = btn["rect"]
        fill = 0 if i==active_idx else 255
        d.rectangle((x0,y0,x1,y1), fill=fill, outline=0)
        color = 255 if i==active_idx else 0

        # multi-line centering
        total_h = 0
        dims = []
        for line in btn["label"]:
            bb = d.textbbox((0,0), line, font=FONT)
            w = bb[2]-bb[0]; h = bb[3]-bb[1]
            dims.append((w,h))
            total_h += h
        total_h += (len(btn["label"])-1)*3

        y_text = y0 + (BUTTON_H - total_h)//2
        for (w,h), line in zip(dims, btn["label"]):
            x_text = x0 + (BUTTON_W - w)//2
            d.text((x_text, y_text), line, font=FONT, fill=color)
            y_text += h + 3

    buf = epd.getbuffer(img.rotate(180))
    epd.displayPartial(buf)

# ─── HIT TEST ──────────────────────────────────────────────────────────────────
def hit(x,y):
    for i,btn in enumerate(BUTTONS):
        x0,y0,x1,y1 = btn["rect"]
        if x0<=x<=x1 and y0<=y<=y1:
            return i
    return None

# ─── UPDATE HANDLER ─────────────────────────────────────────────────────────────
def background_update():
    """Runs Update.py, then shows confirmation and redraws GUI."""
    try:
        subprocess.run(
            ["python3", os.path.expanduser(BUTTONS[1]["script"])],
            cwd=os.path.expanduser(os.path.dirname(BUTTONS[1]["script"])),
            check=True
        )
        print("Update.py finished")
    except Exception as e:
        print("Update.py error:", e)
    # show confirmation
    img = Image.new("1", (DISPLAY_W, DISPLAY_H), 255)
    d   = ImageDraw.Draw(img)
    msg = "Software/settings updated"
    bb  = d.textbbox((0,0), msg, font=FONT)
    d.text(((DISPLAY_W-(bb[2]-bb[0]))//2, (DISPLAY_H-(bb[3]-bb[1]))//2),
           msg, font=FONT, fill=0)
    epd.displayPartial(epd.getbuffer(img.rotate(180)))
    time.sleep(2)
    draw_buttons(None)

# ─── MAIN LOOP ──────────────────────────────────────────────────────────────────
def main():
    draw_buttons(None)
    press_idx   = None
    press_time  = 0

    try:
        while True:
            gt.GT_Scan(GT_Dev, GT_Old)
            rx,ry,s = GT_Dev.X[0], GT_Dev.Y[0], GT_Dev.S[0]
            fx,fy   = DISPLAY_W-rx, DISPLAY_H-ry

            if s>0:
                idx = hit(fx,fy)
                # start timing on first contact
                if press_idx is None and idx is not None:
                    press_idx  = idx
                    press_time = time.time()
                    print(f"Touched button {idx}")
                # if moved outside or touched nothing, cancel
                elif idx != press_idx:
                    press_idx = None
            else:
                # on release, check hold duration
                if press_idx is not None:
                    held = time.time() - press_time
                    if held >= HOLD_TIME:
                        print(f"Button {press_idx} activated")
                        draw_buttons(press_idx)
                        # trigger action
                        if BUTTONS[press_idx]["action"] == "run":
                            os.execvp("python3", ["python3", os.path.expanduser(BUTTONS[0]["script"])])
                        else:
                            # background
                            threading.Thread(target=background_update, daemon=True).start()
                    else:
                        draw_buttons(None)
                    # reset
                    press_idx = None

            time.sleep(0.02)

    finally:
        global _irq_run
        _irq_run = False
        epd.sleep()

if __name__ == "__main__":
    main()
