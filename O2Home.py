#!/usr/bin/env python3
import sys, time, threading, os, subprocess
from TP_lib.gt1151 import GT1151, GT_Development
from TP_lib.epd2in13_V3 import EPD
from PIL import Image, ImageDraw, ImageFont

# Configuration
DISPLAY_W, DISPLAY_H = 250, 122
MARGIN, SPACING     = 5, 10
BUTTON_W            = (DISPLAY_W - 2*MARGIN - SPACING)//2
BUTTON_H            = DISPLAY_H - 2*MARGIN

BUTTONS = [
    { "label_lines": ["Start","O2 sensor"],
      "rect": (MARGIN, MARGIN, MARGIN+BUTTON_W, MARGIN+BUTTON_H)},
    { "label_lines": ["Update","software","and","settings"],
      "rect": (MARGIN+BUTTON_W+SPACING, MARGIN,
               MARGIN+2*BUTTON_W+SPACING, MARGIN+BUTTON_H) }
]

FONT_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
font      = ImageFont.truetype(FONT_PATH, 14)

# Init display & touch
epd    = EPD()
gt     = GT1151()
GT_Dev = GT_Development()
GT_Old = GT_Development()
epd.init(epd.FULL_UPDATE); gt.GT_Init(); epd.Clear(0xFF); epd.init(epd.PART_UPDATE)

_irq_run = True
def touch_irq():
    while _irq_run:
        GT_Dev.Touch = 1 if gt.digital_read(gt.INT)==0 else 0
        time.sleep(0.002)
threading.Thread(target=touch_irq, daemon=True).start()

def draw_buttons(active=None):
    img   = Image.new("1",(DISPLAY_W,DISPLAY_H),255)
    draw  = ImageDraw.Draw(img)
    for i,btn in enumerate(BUTTONS):
        x0,y0,x1,y1 = btn["rect"]
        fill = 0 if i==active else 255
        draw.rectangle((x0,y0,x1,y1),fill=fill,outline=0)
        color = 255 if i==active else 0
        lines = btn["label_lines"]
        heights, widths = [], []
        for L in lines:
            bb = draw.textbbox((0,0),L,font=font)
            widths.append(bb[2]-bb[0]); heights.append(bb[3]-bb[1])
        total_h = sum(heights)+(len(lines)-1)*3
        y_text  = y0 + (BUTTON_H-total_h)//2
        for L,w,h in zip(lines,widths,heights):
            x_text = x0 + (BUTTON_W-w)//2
            draw.text((x_text,y_text),L,font=font,fill=color)
            y_text += h+3
    buf = epd.getbuffer(img.rotate(180))
    epd.displayPartial(buf)

def hit(x,y):
    for i,btn in enumerate(BUTTONS):
        x0,y0,x1,y1 = btn["rect"]
        if x0<=x<=x1 and y0<=y<=y1:
            return i
    return None

def main():
    draw_buttons(None)
    state       = "idle"   # idle, pressing, triggered
    active_btn  = None
    press_start = None

    try:
        while True:
            gt.GT_Scan(GT_Dev,GT_Old)
            rx,ry,s = GT_Dev.X[0],GT_Dev.Y[0],GT_Dev.S[0]
            fx,fy   = DISPLAY_W-rx, DISPLAY_H-ry

            if s>0 and state!="triggered":
                idx = hit(fx,fy)
                # new press
                if state=="idle" and idx is not None:
                    state       = "pressing"
                    active_btn  = idx
                    press_start = time.time()
                    print(f"Touched button {idx}")
                elif state=="pressing":
                    # still pressing same button?
                    if idx!=active_btn:
                        state="idle"
                    elif time.time()-press_start>=1.0:
                        # highlight
                        state="triggered"
                        draw_buttons(active_btn)
                        print(f"Button {active_btn} triggered")
                        # perform action
                        if active_btn==0:
                            os.execvp("python3",["python3",os.path.expanduser("~/O2_Sensor/RunO2.py")])
                        else:
                            # Updating...
                            img = Image.new("1",(DISPLAY_W,DISPLAY_H),255)
                            d   = ImageDraw.Draw(img)
                            msg="Updating..."
                            bb = d.textbbox((0,0),msg,font=font)
                            d.text(((DISPLAY_W-(bb[2]-bb[0]))//2,
                                    (DISPLAY_H-(bb[3]-bb[1]))//2),
                                   msg,font=font,fill=0)
                            epd.displayPartial(epd.getbuffer(img.rotate(180)))
                            # run with cwd
                            subprocess.run(
                              ["python3",os.path.expanduser("~/O2_Sensor/Update.py")],
                              cwd=os.path.expanduser("~/O2_Sensor"),check=True)
                            print("Update.py finished")
                            # confirmation
                            img=Image.new("1",(DISPLAY_W,DISPLAY_H),255)
                            d  = ImageDraw.Draw(img)
                            msg2="Software/settings updated"
                            bb2=d.textbbox((0,0),msg2,font=font)
                            d.text(((DISPLAY_W-(bb2[2]-bb2[0]))//2,
                                    (DISPLAY_H-(bb2[3]-bb2[1]))//2),
                                   msg2,font=font,fill=0)
                            epd.displayPartial(epd.getbuffer(img.rotate(180)))
                            time.sleep(2)
                            draw_buttons(None)
                # else ignore
            else:
                # release or after trigger
                if state!="idle":
                    draw_buttons(None)
                state="idle"
                active_btn=None
                press_start=None

            time.sleep(0.02)

    finally:
        global _irq_run
        _irq_run=False
        epd.sleep()

if __name__=="__main__":
    main()
