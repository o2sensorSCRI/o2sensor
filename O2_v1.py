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
connected = False                # True once we've connected at least once
disconnect_email_sent = False    # To avoid sending multiple “disconnected” emails

# =======================
# Cleanup: always attempt to disconnect sensor,
# send “disconnected” email (once), and log that event
# =======================
def safe_disconnect():
    global dev, connected, disconnect_email_sent

    base = os.path.dirname(__file__)
    log_path = os.path.join(base, f"O2 sensor {sensor_id} log.csv")

    # If we never connected or already emailed, just disconnect (no email)
    if not connected or disconnect_email_sent:
        try:
            if dev:
                dev.disconnect()
            return
        except:
            return

    ts_full = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Log “Disconnected” event
    with open(log_path, "a", newline="") as f:
        csv.writer(f).writerow([ts_full, sensor_id, "Disconnected", "", ""])

    # Build and send “disconnected” email
    subject = f"Alarm - O2 sensor {sensor_id} disconnected"
    body = (
        f"The O₂ sensor {sensor_id} was disconnected at {ts_full}.\n\n"
        f"A copy of the current log is attached."
    )
    send_email(subject, body, [log_path])
    print(f"Disconnection email sent at {ts_full}")
    disconnect_email_sent = True

    try:
        dev.disconnect()
        print("Sensor disconnected cleanly.")
    except Exception as e:
        print(f"Error while disconnecting sensor: {e}")

atexit.register(safe_disconnect)

def _signal_handler(signum, frame):
    print(f"Received signal {signum}; disconnecting sensor and exiting.")
    safe_disconnect()
    sys.exit(0)

signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)

# =======================
# Email helper (unchanged)
# =======================
def send_email(subject, body, attachments=[]):
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, sender, ", ".join(recips)
    msg.set_content(body)
    for p in attachments:
        try:
            with open(p, "rb") as f:
                data = f.read()
            msg.add_attachment(
                data,
                maintype="application",
                subtype="octet-stream",
                filename=os.path.basename(p),
            )
        except FileNotFoundError:
            print(f"Missing attachment: {p}")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(sender, pw)
            s.send_message(msg)
    except Exception as e:
        print(f"Email failed '{subject}': {e}")

# =======================
# Load configuration
# =======================
cfg = configparser.ConfigParser()
cfg.read("O2_sensor.cfg")

sensor_id      = cfg["SensorSettings"]["sensor_id"].strip("'\"")
o2_corr        = float(cfg["SensorSettings"]["O2_sensor_cf"])
o2_ref         = float(cfg["SensorSettings"]["O2_ref"])
o2_thr         = float(cfg["SensorSettings"]["O2_threshold"])
recips         = [e.strip() for e in cfg["Email"]["recipients"].split(",")]
sender         = cfg["Email"]["sender_email"]
pw             = cfg["Email"]["app_password"]

# Logging intervals (seconds)
logtime        = int(cfg["SensorSettings"]["logtime"])
logtime_alarm  = int(cfg["SensorSettings"]["logtime_alarm"])

# =======================
# Initialize e-Paper display
# =======================
epd = epd_driver.EPD()
epd.init(epd.FULL_UPDATE)
epd.Clear(0xFF)  # white

# The 2.13″ V3 is 250×122 (width × height)
display_width  = epd.width   # 250
display_height = epd.height  # 122

# Load fonts (make sure these paths exist on your Pi)
font_24 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
font_12 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)

# A helper to redraw the entire screen
def update_eink(time_str, o2_str, rh_str, temp_str):
    # Create a blank white image
    img = Image.new("1", (display_width, display_height), 255)
    draw = ImageDraw.Draw(img)

    # Draw time in top-left
    draw.text((5, 5), time_str, font=font_12, fill=0)

    # Draw sensor ID in top-right
    id_text = f"ID {sensor_id}"
    bbox_id = draw.textbbox((0, 0), id_text, font=font_12)
    w_id = bbox_id[2] - bbox_id[0]
    draw.text((display_width - w_id - 5, 5), id_text, font=font_12, fill=0)

    # Draw O₂ reading centered vertically
    bbox_o2 = draw.textbbox((0, 0), o2_str, font=font_24)
    w_o2 = bbox_o2[2] - bbox_o2[0]
    h_o2 = bbox_o2[3] - bbox_o2[1]
    x_o2 = (display_width - w_o2) // 2
    y_o2 = (display_height - h_o2) // 2 - 10
    draw.text((x_o2, y_o2), o2_str, font=font_24, fill=0)

    # Draw RH in bottom-left
    draw.text((5, display_height - 20), rh_str, font=font_12, fill=0)

    # Draw Temp in bottom-right
    bbox_temp = draw.textbbox((0, 0), temp_str, font=font_12)
    w_temp = bbox_temp[2] - bbox_temp[0]
    draw.text((display_width - w_temp - 5, display_height - 20), temp_str, font=font_12, fill=0)

    # Full update to e-ink
    epd.display(epd.getbuffer(img))

# =======================
# Main monitoring loop
# =======================
def monitor():
    global dev, connected

    base = os.path.dirname(__file__)
    log_path  = os.path.join(base, f"O2 sensor {sensor_id} log.csv")
    alog_path = os.path.join(base, f"O2 sensor {sensor_id} alarm log.csv")

    # Ensure log files exist with headers
    if not os.path.isfile(log_path):
        with open(log_path, "w", newline="") as f:
            csv.writer(f).writerow(["Date & Time", "Sensor", "O2%", "Temp", "RH"])
    if not os.path.isfile(alog_path):
        with open(alog_path, "w", newline="") as f:
            csv.writer(f).writerow(["Sensor", "Start", "End", "Duration", "MaxDev", "Recipients"])

    dev = PASCOBLEDevice()

    # Step 1: Connect loop (retry until successful)
    while True:
        try:
            dev.connect_by_id(sensor_id)
            print(f"Connected to sensor {sensor_id}")

            # Step 2: Read initial values, log them, log “Connected” event, send initiation email
            try:
                data_init = dev.read_data_list(["OxygenGasConcentration", "Temperature", "RelativeHumidity"])
                o2_init  = data_init["OxygenGasConcentration"] + o2_corr
                tmp_init = data_init["Temperature"]
                rh_init  = data_init["RelativeHumidity"]
            except Exception as e:
                print(f"Initial read error: {e}. Using placeholders.")
                o2_init, tmp_init, rh_init = (o2_ref, 0.0, 0.0)

            ts_full = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Log initial sensor values
            with open(log_path, "a", newline="") as f:
                csv.writer(f).writerow([
                    ts_full, sensor_id,
