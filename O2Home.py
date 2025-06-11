#!/usr/bin/env python3
import sys, time, threading, os, subprocess
from TP_lib.gt1151 import GT1151, GT_Development
from TP_lib.epd2in13_V3 import EPD
from PIL import Image, ImageDraw, ImageFont

# ─── CONFIG ─────────────────────────────────────────────────────────────────────
DISPLAY_W, DISPLAY_H = 250, 122
MARGIN, SPACING     = 5, 10
BUTTON_W            = (DISPLAY_W - 2*MARGIN - SPACING)//2
BUTTON_H            = DISPLAY_H - 2*MARGIN
HOLD_TIME           = 1.0   # seconds to hold

BUTTONS = [
    {
        "label": ["Start","O2 sensor"],
        "rect": (MARGIN, MARGIN, MARGIN+BUTTON_W, MARGIN+BUTTON_H),
        "type": "exec",    # replace GUI
        "script": "~/O2_Sensor/RunO2.py"
    },
    {
        "label": ["Update","software","and","settings"],
        "rect": (MARGIN+BUTTON_W+SPACING, MARGIN,
                 MARGIN+2*BUTTON_W+SPACING, MARGIN+BUTTON_H),
        "type": "background",  # background thread
        "script": "~/O2_Sensor/Update.py"
    }
]

FONT = ImageFont.truetype(
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 14)

# ─── SETUP EPD & TOUCH ──────────────────────────────────────────────────────────
epd    = EPD()
gt     = GT1151()
GT_Dev = GT_Development()
GT_Old = GT_Development()
epd.init(epd.FULL_UPDATE); gt.GT_Init(); epd.Clear(0xFF); epd.init(epd.PART_UPDATE)

irq_run = True
def irq_thread():
    while irq_run:
        GT_Dev.Touch = 1 if gt.digital_read(gt.INT)==0 else 0
        time.sleep(0.002)
threading.Thread(target=irq_thread, daemon=True).start()

# ─── DRAW UTILITY ────────────────────────────────────────────────────────────────
def draw_buttons(active=None):
    img  = Image.new("1", (DISPLAY_W, DISPLAY_H), 255)
    draw = ImageDraw.Draw(img)
    for i,btn in enumerate(BUTTONS):
        x0,y0,x1,y1 = btn["rect"]
        fill = 0 if i==active else 255
        draw.rectangle((x0,y0,x1,y1), fill=fill, outline=0)
        color = 255 if i==active else 0
        # multi-line center
        lines = btn["label"]
        total_h = sum(draw.textbbox((0,0), L, font=FONT)[3] - draw.textbbox((0,0), L, font=FONT)[1]
                      for L in lines) + (len(lines)-1)*3
        y_text = y0 + (BUTTON_H - total_h)//2
        for L in lines:
            bb = draw.textbbox((0,0), L, font=FONT)
            w = bb[2]-bb[0]; h = bb[3]-bb[1]
            x_text = x0 + (BUTTON_W - w)//2
            draw.text((x_text, y_text), L, font=FONT, fill=color)
            y_text += h + 3

    buf = epd.getbuffer(img.rotate(180))
    epd.displayPartial(buf)

# ─── HIT TEST ───────────────────────────────────────────────────────────────────
def hit(x,y):
    for i,btn in enumerate(BUTTONS):
        x0,y0,x1,y1=btn["rect"]
        if x0<=x<=x1 and y0<=y<=y1:
            return i
    return None

# ─── UPDATE HANDLER ─────────────────────────────────────────────────────────────
def background_update():
    script = os.path.expanduser(BUTTONS[1]["script"])
    cwd    = os.path.dirname(script)
    try:
        subprocess.run(["python3", script], cwd=cwd, check=True)
        print("Update.py finished")
    except Exception as e:
        print("Update error:", e)
    # confirmation
    img  = Image.new("1", (DISPLAY_W, DISPLAY_H), 255)
    draw = ImageDraw.Draw(img)
    msg  = "Software/settings updated"
    bb   = draw.textbbox((0,0), msg, font=FONT)
    draw.text(((DISPLAY_W-(bb[2]-bb[0]))//2,
               (DISPLAY_H-(bb[3]-bb[1]))//2),
              msg, font=FONT, fill=0)
    epd.displayPartial(epd.getbuffer(img.rotate(180)))
    time.sleep(2)
    draw_buttons(None)

# ─── MAIN LOOP ──────────────────────────────────────────────────────────────────
def main():
    draw_buttons(None)
    pressed_idx  = None
    press_time   = None

    try:
        while True:
            gt.GT_Scan(GT_Dev, GT_Old)
            rx,ry,s = GT_Dev.X[0], GT_Dev.Y[0], GT_Dev.S[0]
            fx,fy   = DISPLAY_W-rx, DISPLAY_H-ry

            if GT_Dev.Touch == 1:
                idx = hit(fx,fy)
                if pressed_idx is None and idx is not None:
                    # finger down on a button
                    pressed_idx = idx
                    press_time  = time.time()
                    print(f"Touched button {idx}")
                # else ignore
            else:
                # finger up
                if pressed_idx is not None:
                    held = time.time() - press_time
                    if held >= HOLD_TIME:
                        # activate
                        print(f"Button {pressed_idx} activated after {held:.2f}s")
                        draw_buttons(pressed_idx)
                        btn = BUTTONS[pressed_idx]
                        if btn["type"] == "exec":
                            # replace GUI
                            script = os.path.expanduser(btn["script"])
                            os.execvp("python3", ["python3", script])
                        else:
                            # background update
                            threading.Thread(target=background_update, daemon=True).start()
                    else:
                        # too quick, just redraw
                        draw_buttons(None)
                    pressed_idx = None
                    press_time  = None

            time.sleep(0.02)

    finally:
        global irq_run
        irq_run = False
        epd.sleep()

if __name__ == "__main__":
    main()
