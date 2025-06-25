import time
import os
import csv
import configparser
import smtplib
import threading
import sys
import signal
import atexit
from datetime import datetime, date
from email.message import EmailMessage

# ─── e-Paper (2.13″ V3) display imports ───
from waveshare_epd import epd2in13_V3 as epd_driver
from PIL import Image, ImageDraw, ImageFont

from pasco import PASCOBLEDevice

# =======================
# Module-level references & flags
# =======================
dev = None
connected = False
disconnect_email_sent = False

# =======================
# Load configuration
# =======================
cfg = configparser.ConfigParser()
cfg.read("O2_sensor.cfg")

sensor_id             = cfg["SensorSettings"]["sensor_id"].strip("'\"")
o2_ref                = float(cfg["SensorSettings"]["O2_ref"])
o2_thr                = float(cfg["SensorSettings"]["O2_threshold"])
o2_sensor_cf_intercept = float(cfg["SensorSettings"]["o2_sensor_cf_intercept"])
o2_sensor_cf_slope     = float(cfg["SensorSettings"]["o2_sensor_cf_slope"])

recips  = [e.strip() for e in cfg["Email"]["recipients"].split(",")]
sender  = cfg["Email"]["sender_email"]
pw      = cfg["Email"]["app_password"]

logtime       = int(cfg["SensorSettings"]["logtime"])
logtime_alarm = int(cfg["SensorSettings"]["logtime_alarm"])

# =======================
# Initialize e-Paper display (full refresh)
# =======================
epd = epd_driver.EPD()
epd.init(epd.FULL_UPDATE)
epd.Clear(0xFF)

display_w, display_h = epd.width, epd.height   # 250×122
land_w, land_h       = display_h, display_w   # 122×250

# =======================
# Load fonts
# =======================
font_o2   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 38)
font_lbl  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
font_disc = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)

def update_eink(time_str, o2_str, rh_str, temp_str, full=False):
    mode = epd.FULL_UPDATE if full else epd.PART_UPDATE
    epd.init(mode)

    img  = Image.new("1", (land_w, land_h), 255)
    draw = ImageDraw.Draw(img)

    if full:
        bbox = draw.textbbox((0,0), o2_str, font=font_o2)
        x = (land_w - (bbox[2]-bbox[0])) // 2
        y = (land_h - (bbox[3]-bbox[1])) // 2 - 10
        draw.text((x,y), o2_str, font=font_o2, fill=0)
    else:
        draw.text((5,5), time_str, font=font_lbl, fill=0)
        id_txt = f"ID {sensor_id}"
        bbox  = draw.textbbox((0,0), id_txt, font=font_lbl)
        draw.text((land_w-(bbox[2]-bbox[0])-5,5), id_txt, font=font_lbl, fill=0)

        bbox = draw.textbbox((0,0), o2_str, font=font_o2)
        x = (land_w - (bbox[2]-bbox[0])) // 2
        y = (land_h - (bbox[3]-bbox[1])) // 2 - 10
        draw.text((x,y), o2_str, font=font_o2, fill=0)

        draw.text((5, land_h-20), rh_str, font=font_lbl, fill=0)
        bbox = draw.textbbox((0,0), temp_str, font=font_lbl)
        draw.text((land_w-(bbox[2]-bbox[0])-5, land_h-20), temp_str, font=font_lbl, fill=0)

    buf = epd.getbuffer(img.rotate(-90, expand=True))
    if full:
        epd.display(buf)
    else:
        epd.displayPartial(buf)

def display_disconnected():
    epd.init(epd.FULL_UPDATE)
    img  = Image.new("1", (land_w, land_h), 0)
    draw = ImageDraw.Draw(img)

    lines  = ["SENSOR", "DISCONNECTED"]
    total_h = sum(
        draw.textbbox((0,0), l, font=font_disc)[3] - draw.textbbox((0,0), l, font=font_disc)[1]
        for l in lines
    ) + 4
    y = (land_h - total_h)//2
    for l in lines:
        bbox = draw.textbbox((0,0), l, font=font_disc)
        w    = bbox[2] - bbox[0]
        x    = (land_w - w)//2
        draw.text((x,y), l, font=font_disc, fill=255)
        y += (bbox[3]-bbox[1]) + 4

    buf = epd.getbuffer(img.rotate(-90, expand=True))
    epd.display(buf)

def send_email(subject, body, attachments=None, recipients=None):
    to_list = recips if recipients is None else recipients
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"]    = sender
    msg["To"]      = ", ".join(to_list)
    msg.set_content(body)

    if attachments:
        for p in attachments:
            try:
                with open(p, 'rb') as f:
                    data = f.read()
                msg.add_attachment(
                    data,
                    maintype='application',
                    subtype='octet-stream',
                    filename=os.path.basename(p)
                )
            except FileNotFoundError:
                print(f"Missing attachment: {p}")

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(sender, pw)
            s.send_message(msg)
    except Exception as e:
        print(f"Email failed '{subject}': {e}")

def safe_disconnect():
    global dev, connected, disconnect_email_sent
    if not connected or disconnect_email_sent:
        try: dev.disconnect()
        except: pass
        return

    base    = os.path.dirname(__file__)
    logpath = os.path.join(base, f"O2 sensor {sensor_id} log.csv")
    ts      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(logpath,'a',newline='') as f:
        csv.writer(f).writerow([ts, sensor_id, "Disconnected", "", ""])

    subj = f"Alarm - O2 sensor {sensor_id} disconnected"
    body = f"The O₂ sensor {sensor_id} was disconnected at {ts}.\n\nCopy of log attached."

    display_disconnected()
    disconnect_email_sent = True
    send_email(subj, body, attachments=[logpath])
    print(f"Disconnection email sent at {ts}")

    try: dev.disconnect()
    except Exception as e: print(f"Error during disconnect: {e}")

atexit.register(safe_disconnect)
signal.signal(signal.SIGINT,  lambda s,f: (safe_disconnect(), sys.exit(0)))
signal.signal(signal.SIGTERM, lambda s,f: (safe_disconnect(), sys.exit(0)))

def monitor():
    global dev, connected, disconnect_email_sent
    base     = os.path.dirname(__file__)
    logpath  = os.path.join(base, f"O2 sensor {sensor_id} log.csv")
    alogpath = os.path.join(base, f"O2 sensor {sensor_id} alarm log.csv")

    # Ensure log files exist (with headers)
    if not os.path.isfile(logpath):
        with open(logpath,'w',newline='') as f:
            csv.writer(f).writerow(["Date & Time","Sensor","O2%","Temp","RH"])
    if not os.path.isfile(alogpath):
        with open(alogpath,'w',newline='') as f:
            csv.writer(f).writerow([
                "Sensor","Start","End","Duration","MaxDev","Recipients"
            ])

    dev = PASCOBLEDevice()

    # Initial connect & display first values (full refresh)
    while True:
        try:
            dev.connect_by_id(sensor_id)
            d = dev.read_data_list([
                "OxygenGasConcentration","Temperature","RelativeHumidity"
            ])

            raw  = d["OxygenGasConcentration"]
            o2_i = (raw - o2_sensor_cf_intercept) / o2_sensor_cf_slope
            t_i  = d["Temperature"]
            rh_i = d["RelativeHumidity"]

            ts0 = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(logpath,'a',newline='') as f:
                csv.writer(f).writerow([
                    ts0, sensor_id,
                    f"{o2_i:.1f}", f"{t_i:.1f}", f"{rh_i:.1f}"
                ])
            with open(logpath,'a',newline='') as f:
                csv.writer(f).writerow([ts0, sensor_id, "Connected", "", ""])

            subj0 = f"O2 sensor {sensor_id} initiated"
            body0 = (
                f"The O₂ sensor {sensor_id} was initiated at {ts0}.\n\n"
                f"Initial readings:\n"
                f"• O₂: {o2_i:.1f}%\n"
                f"• Temp: {t_i:.1f}°C\n"
                f"• RH: {rh_i:.1f}%\n\n"
                "Copy of log attached."
            )
            send_email(subj0, body0, attachments=[logpath])
            update_eink(
                ts0[11:16],
                f"O₂: {o2_i:.1f}%",
                f"RH: {rh_i:.1f}%",
                f"Temp: {t_i:.1f}°C",
                full=True
            )

            connected = True
            break

        except Exception as e:
            print(f"Connection failed: {e}. Retrying…")
            time.sleep(5)

    alarm     = False
    start     = None
    deviated  = []
    last_alarm= 0
    last_log  = time.time()
    last_eink = time.time() - 2  # 2s interval
    last_day  = date.today()

    while True:
        if disconnect_email_sent:
            display_disconnected()
            break

        try:
            d = dev.read_data_list([
                "OxygenGasConcentration","Temperature","RelativeHumidity"
            ])
        except:
            print("Read error; reconnecting…")
            try: dev.disconnect()
            except: pass
            time.sleep(1)
            continue

        raw  = d["OxygenGasConcentration"]
        o2v  = (raw - o2_sensor_cf_intercept) / o2_sensor_cf_slope
        tv   = d["Temperature"]
        rhv  = d["RelativeHumidity"]
        now  = datetime.now()
        ts   = now.strftime("%Y-%m-%d %H:%M:%S")
        sm   = ts[11:16]

        if not disconnect_email_sent:
            print(f"{ts} | O₂: {o2v:.1f}% | Temp: {tv:.1f}°C | RH: {rhv:.1f}%")
            if time.time() - last_eink >= 2:
                update_eink(
                    sm,
                    f"O₂: {o2v:.1f}%",
                    f"RH: {rhv:.1f}%",
                    f"Temp: {tv:.1f}°C",
                    full=False
                )
                last_eink = time.time()

        deviate = abs(o2v - o2_ref)
        if deviate > o2_thr:
            subjA = f"ALARM - O2 sensor {sensor_id} change"
            bodyA = (
                f"O₂ changed >{o2_thr:.1f}% from {o2_ref:.1f}% at {ts}.\n"
                f"Current: O₂ {o2v:.1f}% | Temp {tv:.1f}°C | RH {rhv:.1f}%"
            )
            if not alarm:
                alarm = True
                start = now
                deviated = [o2v]
                with open(logpath,'a',newline='') as f:
                    csv.writer(f).writerow([ts, sensor_id, f"{o2v:.1f}", f"{tv:.1f}", f"{rhv:.1f}"])
                with open(logpath,'a',newline='') as f:
                    csv.writer(f).writerow([ts, sensor_id, 'Alarm triggered','',''])
                send_email(subjA, bodyA, attachments=[logpath, alogpath])
                print(f"Alarm email sent at {ts}")
                last_alarm = time.time()
            else:
                deviated.append(o2v)
                if time.time() - last_alarm >= logtime_alarm:
                    with open(logpath,'a',newline='') as f:
                        csv.writer(f).writerow([ts, sensor_id, f"{o2v:.1f}", f"{tv:.1f}", f"{rhv:.1f}"])
                    send_email(subjA, bodyA, attachments=[logpath, alogpath])
                    print(f"Repeat alarm at {ts}")
                    last_alarm = time.time()
        else:
            if alarm:
                end = now
                dur = end - start
                maxd = max(deviated, key=lambda x: abs(x - o2_ref))
                with open(logpath,'a',newline='') as f:
                    csv.writer(f).writerow([ts, sensor_id, f"{o2v:.1f}", f"{tv:.1f}", f"{rhv:.1f}"])
                with open(logpath,'a',newline='') as f:
                    csv.writer(f).writerow([ts, sensor_id, 'Alarm deactivated','',''])
                with open(alogpath,'a',newline='') as f:
                    csv.writer(f).writerow([
                        sensor_id,
                        start.strftime("%Y-%m-%d %H:%M:%S"),
                        end.strftime("%Y-%m-%d %H:%M:%S"),
                        str(dur).split('.')[0],
                        f"{maxd:.2f}",
                        ",".join(recips),
                    ])
                subjR = f"O₂ level restored for {sensor_id}"
                bodyR = (
                    f"O₂ returned within ±{o2_thr:.1f}% at {ts}.\n"
                    f"Current: O₂ {o2v:.1f}% | Temp {tv:.1f}°C | RH {rhv:.1f}%"
                )
                send_email(subjR, bodyR, attachments=[logpath, alogpath])
                print(f"Restoration email sent at {ts}")
                alarm = False

        # periodic logging
        interval = logtime_alarm if alarm else logtime
        if time.time() - last_log >= interval:
            with open(logpath,'a',newline='') as f:
                csv.writer(f).writerow([ts, sensor_id, f"{o2v:.1f}", f"{tv:.1f}", f"{rhv:.1f}"])
            last_log = time.time()

        # daily summary — send daily log for previous day at first reading of new day
        if now.date() != last_day:
            td = last_day.strftime("%Y-%m-%d")
            subjD = f"O2 sensor {sensor_id} - {td} daily log"
            bodyD = f"Attached is the daily log for {td}."
            send_email(subjD, bodyD,
                       attachments=[logpath],
                       recipients=["o2sensor.scri@gmail.com"])
            print(f"Daily log email sent for {td} at {ts}")
            last_day = now.date()

        time.sleep(2)

# Start monitoring in background
threading.Thread(target=monitor, daemon=True).start()

# Keep script alive
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    safe_disconnect()
    sys.exit(0)
