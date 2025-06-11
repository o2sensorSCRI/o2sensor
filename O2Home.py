#!/usr/bin/env python3
import sys, time, threading, os, subprocess
from TP_lib.gt1151 import GT1151, GT_Development
from TP_lib.epd2in13_V3 import EPD
from PIL import Image, ImageDraw, ImageFont

# ─── CONFIG ─────────────────────────────────────────────────────────────────────
W, H         = 250, 122
MGR, SP      = 5, 10
BW           = (W - 2*MGR - SP)//2
BH           = H - 2*MGR
HOLD_SEC     = 1.0

BUTTONS = [
    { "label": ["Start","O₂ sensor"],
      "rect": (MGR, MGR, MGR+BW, MGR+BH),
      "mode": "exec",
      "script": "~/O2_Sensor/RunO2.py"
    },
    { "label": ["Update","software","and","settings"],
      "rect": (MGR+BW+SP, MGR, MGR+2*BW+SP, MGR+BH),
      "mode": "bg",
      "script": "~/O2_Sensor/Update.py"
    }
]

FONT = ImageFont.truetype(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)

# ─── SETUP ────────────────────────────────────────────────────────────────────────
epd    = EPD()
gt     = GT1151()
GT_Dev = GT_Development()
GT_Old = GT_Development()
epd.init(epd.FULL_UPDATE); gt.GT_Init(); epd.Clear(0xFF); epd.init(epd.PART_UPDATE)

_running = True
def irq_loop():
    while _running:
        GT_Dev.Touch = 1 if gt.digital_read(gt.INT)==0 else 0
        time.sleep(0.002)
threading.Thread(target=irq_loop, daemon=True).start()

# ─── DRAW ────────────────────────────────────────────────────────────────────────
def draw(active=None):
    img  = Image.new("1",(W,H),255)
    d    = ImageDraw.Draw(img)
    for i,b in enumerate(BUTTONS):
        x0,y0,x1,y1 = b["rect"]
        fill = 0 if i==active else 255
        d.rectangle((x0,y0,x1,y1), fill=fill, outline=0)
        col = 255 if i==active else 0

        # center multiline
        lines = b["label"]
        total_h = sum(d.textbbox((0,0),L,font=FONT)[3]-d.textbbox((0,0),L,font=FONT)[1]
                       for L in lines) + (len(lines)-1)*3
        y_text = y0 + (BH-total_h)//2
        for L in lines:
            bb = d.textbbox((0,0),L,font=FONT)
            w,h = bb[2]-bb[0], bb[3]-bb[1]
            x_text = x0 + (BW-w)//2
            d.text((x_text,y_text),L,font=FONT,fill=col)
            y_text += h+3

    buf = epd.getbuffer(img.rotate(180))
    epd.displayPartial(buf)

# ─── HIT TEST ───────────────────────────────────────────────────────────────────
def hit(x,y):
    for i,b in enumerate(BUTTONS):
        x0,y0,x1,y1 = b["rect"]
        if x0<=x<=x1 and y0<=y<=y1:
            return i
    return None

# ─── BACKGROUND UPDATE ───────────────────────────────────────────────────────────
def background_update():
    path = os.path.expanduser(BUTTONS[1]["script"])
    cwd  = os.path.dirname(path)
    try:
        subprocess.run(["python3", path], cwd=cwd, check=True)
        print("Update.py finished")
    except Exception as e:
        print("Update error:", e)
    # confirmation
    img = Image.new("1",(W,H),255)
    d   = ImageDraw.Draw(img)
    msg = "Software/settings updated"
    bb  = d.textbbox((0,0),msg,font=FONT)
    d.text(((W-(bb[2]-bb[0]))//2,(H-(bb[3]-bb[1]))//2), msg, font=FONT, fill=0)
    epd.displayPartial(epd.getbuffer(img.rotate(180)))
    time.sleep(2)
    draw(None)

# ─── MAIN LOOP ──────────────────────────────────────────────────────────────────
def main():
    draw(None)
    pressed_idx = None
    press_time  = 0

    try:
        while True:
            gt.GT_Scan(GT_Dev, GT_Old)
            rx,ry = GT_Dev.X[0], GT_Dev.Y[0]
            fx,fy = W-rx, H-ry

            if GT_Dev.Touch == 1 and pressed_idx is None:
                idx = hit(fx,fy)
                if idx is not None:
                    pressed_idx = idx
                    press_time  = time.time()
                    print(f"Finger down on button {idx}")
            elif GT_Dev.Touch == 0 and pressed_idx is not None:
                held = time.time() - press_time
                idx  = pressed_idx
                pressed_idx = None
                if held >= HOLD_SEC:
                    print(f"Button {idx} activated after {held:.2f}s")
                    draw(idx)
                    mode   = BUTTONS[idx]["mode"]
                    script = os.path.expanduser(BUTTONS[idx]["script"])
                    if mode == "exec":
                        os.execvp("python3", ["python3", script])
                    else:
                        threading.Thread(target=background_update, daemon=True).start()
                else:
                    draw(None)

            time.sleep(0.02)
    finally:
        global _running
        _running = False
        epd.sleep()

if __name__=="__main__":
    main()
