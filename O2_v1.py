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

sensor_id     = cfg["SensorSettings"]["sensor_id"].strip("'\"")
o2_corr       = float(cfg["SensorSettings"]["O2_sensor_cf"])
o2_ref        = float(cfg["SensorSettings"]["O2_ref"])
o2_thr        = float(cfg["SensorSettings"]["O2_threshold"])
recips        = [e.strip() for e in cfg["Email"]["recipients"].split(",")]
sender        = cfg["Email"]["sender_email"]
pw            = cfg["Email"]["app_password"]

logtime       = int(cfg["SensorSettings"]["logtime"])
logtime_alarm = int(cfg["SensorSettings"]["logtime_alarm"])

# =======================
# Initialize e-Paper display
# =======================
epd = epd_driver.EPD()
epd.init(epd.FULL_UPDATE)
epd.Clear(0xFF)

display_width, display_height = epd.width, epd.height   # 250×122
land_width, land_height       = display_height, display_width  # 122×250 canvas

# ↑ O₂ font increased 20%: 32→38
font_o2 = ImageFont.truetype(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 38
)
font_lbl = ImageFont.truetype(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12
)

def update_eink(time_str, o2_str, rh_str, temp_str):
    img_land = Image.new("1", (land_width, land_height), 255)
    draw = ImageDraw.Draw(img_land)

    # time
    draw.text((5, 5), time_str, font=font_lbl, fill=0)

    # device ID
    id_txt = f"ID {sensor_id}"
    bbox = draw.textbbox((0, 0), id_txt, font=font_lbl)
    draw.text((land_width - (bbox[2]-bbox[0]) - 5, 5), id_txt, font=font_lbl, fill=0)

    # O₂
    bbox = draw.textbbox((0, 0), o2_str, font=font_o2)
    x = (land_width - (bbox[2]-bbox[0]))//2
    y = (land_height - (bbox[3]-bbox[1]))//2 - 10
    draw.text((x, y), o2_str, font=font_o2, fill=0)

    # RH & Temp
    draw.text((5, land_height - 20), rh_str,   font=font_lbl, fill=0)
    bbox = draw.textbbox((0, 0), temp_str, font=font_lbl)
    draw.text((land_width - (bbox[2]-bbox[0]) - 5, land_height - 20),
              temp_str, font=font_lbl, fill=0)

    img_rot = img_land.rotate(-90, expand=True)
    epd.display(epd.getbuffer(img_rot))

def display_disconnected():
    img_land = Image.new("1", (land_width, land_height), 255)
    draw = ImageDraw.Draw(img_land)

    text = "Disconnected"
    bbox = draw.textbbox((0, 0), text, font=font_o2)
    x = (land_width - (bbox[2]-bbox[0]))//2
    y = (land_height - (bbox[3]-bbox[1]))//2
    draw.text((x, y), text, font=font_o2, fill=0)

    img_rot = img_land.rotate(-90, expand=True)
    epd.display(epd.getbuffer(img_rot))

# =======================
# Email helper
# =======================
def send_email(subject, body, attachments=[]):
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, sender, ", ".join(recips)
    msg.set_content(body)
    for p in attachments:
        try:
            with open(p, "rb") as f:
                data = f.read()
            msg.add_attachment(data,
                               maintype="application",
                               subtype="octet-stream",
                               filename=os.path.basename(p))
        except FileNotFoundError:
            print(f"Missing attachment: {p}")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(sender, pw)
            s.send_message(msg)
    except Exception as e:
        print(f"Email failed '{subject}': {e}")

# =======================
# Cleanup: handle disconnect
# =======================
def safe_disconnect():
    global dev, connected, disconnect_email_sent

    if not connected or disconnect_email_sent:
        try:
            if dev: dev.disconnect()
        except: pass
        return

    base    = os.path.dirname(__file__)
    logpath = os.path.join(base, f"O2 sensor {sensor_id} log.csv")
    ts      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # log event
    with open(logpath, "a", newline="") as f:
        csv.writer(f).writerow([ts, sensor_id, "Disconnected", "", ""])

    # send email
    subj = f"Alarm - O2 sensor {sensor_id} disconnected"
    body = (f"The O₂ sensor {sensor_id} was disconnected at {ts}.\n\n"
            "A copy of the current log is attached.")
    send_email(subj, body, [logpath])
    print(f"Disconnection email sent at {ts}")

    # update display: only “Disconnected”
    display_disconnected()

    disconnect_email_sent = True
    try:
        dev.disconnect()
    except Exception as e:
        print(f"Error during disconnect: {e}")

atexit.register(safe_disconnect)
signal.signal(signal.SIGINT,  _signal_handler:=lambda s,f:(safe_disconnect(), sys.exit(0)))
signal.signal(signal.SIGTERM, _signal_handler)

# =======================
# Main monitoring loop
# =======================
def monitor():
    global dev, connected

    base     = os.path.dirname(__file__)
    logpath  = os.path.join(base, f"O2 sensor {sensor_id} log.csv")
    alogpath = os.path.join(base, f"O2 sensor {sensor_id} alarm log.csv")

    # ensure logs
    if not os.path.isfile(logpath):
        with open(logpath, "w", newline="") as f:
            csv.writer(f).writerow(["Date & Time","Sensor","O2%","Temp","RH"])
    if not os.path.isfile(alogpath):
        with open(alogpath, "w", newline="") as f:
            csv.writer(f).writerow(["Sensor","Start","End","Duration","MaxDev","Recipients"])

    dev = PASCOBLEDevice()

    # connect & initiate
    while True:
        try:
            dev.connect_by_id(sensor_id)
            print(f"Connected to sensor {sensor_id}")

            # initial read
            try:
                d = dev.read_data_list(["OxygenGasConcentration","Temperature","RelativeHumidity"])
                o2_i = d["OxygenGasConcentration"] + o2_corr
                t_i  = d["Temperature"]
                rh_i = d["RelativeHumidity"]
            except:
                o2_i, t_i, rh_i = (o2_ref,0,0)

            ts0 = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(logpath,"a",newline="") as f:
                csv.writer(f).writerow([ts0,sensor_id,f"{o2_i:.1f}",f"{t_i:.1f}",f"{rh_i:.1f}"])
            with open(logpath,"a",newline="") as f:
                csv.writer(f).writerow([ts0,sensor_id,"Connected","",""])

            subj0 = f"O₂ sensor {sensor_id} initiated"
            body0 = (f"The O₂ sensor {sensor_id} was initiated at {ts0}.\n\n"
                     f"Initial readings:\n"
                     f"• O₂: {o2_i:.1f}%\n"
                     f"• Temperature: {t_i:.1f}°C\n"
                     f"• Humidity: {rh_i:.1f}%\n\n"
                     "A copy of the current log is attached.")
            send_email(subj0, body0, [logpath])
            print(f"Initiation email sent at {ts0}")

            connected = True
            break
        except Exception as e:
            print(f"Connection failed: {e}. Retrying…")
            time.sleep(5)

    alarm = False
    start = None
    deviated = []
    last_alarm = 0
    last_log   = time.time()
    last_eink  = time.time() - 20
    last_day   = None

    # first display
    update_eink("--:--","O₂: --.-%","RH: --.-%","Temp: --.-°C")

    while True:
        try:
            d = dev.read_data_list(["OxygenGasConcentration","Temperature","RelativeHumidity"])
        except:
            print("Read error; reconnecting…")
            try: dev.disconnect()
            except: pass
            time.sleep(1)
            continue

        o2v = d["OxygenGasConcentration"] + o2_corr
        tv  = d["Temperature"]
        rhv = d["RelativeHumidity"]
        now = datetime.now()
        ts  = now.strftime("%Y-%m-%d %H:%M:%S")
        sm  = ts[11:16]

        # terminal print every 2s
        print(f"{ts} | O₂: {o2v:.1f}% | Temp: {tv:.1f}°C | RH: {rhv:.1f}%")

        # e-ink update every 20s
        if time.time() - last_eink >= 20:
            update_eink(sm,
                        f"O₂: {o2v:.1f}%",
                        f"RH: {rhv:.1f}%",
                        f"Temp: {tv:.1f}°C")
            last_eink = time.time()

        # … rest of alarm logic and periodic/daily logging unchanged …

        time.sleep(2)

threading.Thread(target=monitor, daemon=True).start()

# keep alive
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    safe_disconnect()
