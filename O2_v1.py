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

# ─── e-Paper (2.13” V3) display imports ───
from waveshare_epd import epd2in13_V3 as epd_driver
from PIL import Image, ImageDraw, ImageFont

from pasco import PASCOBLEDevice

# =======================
# Module-level references & flags
# =======================
dev = None
connected = False                # True once we've connected at least once
disconnect_email_sent = False    # To avoid duplicate “disconnected” emails

# =======================
# Cleanup: disconnect sensor, send “disconnected” email, log event
# =======================
def safe_disconnect():
    global dev, connected, disconnect_email_sent

    base = os.path.dirname(__file__)
    log_path = os.path.join(base, f"O2 sensor {sensor_id} log.csv")

    # If we never connected or already emailed, just attempt disconnect
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

    # Send “disconnected” email
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

# We'll use a 24px font for the O₂ reading, and a smaller 12px for other text
font_24 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
font_12 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)

# A helper to update the e-Paper with current readings
def update_eink(time_str, o2_str, rh_str, temp_str):
    # Create a new blank image (1-bit color: 0=black, 255=white)
    img = Image.new("1", (epd.height, epd.width), 255)
    draw = ImageDraw.Draw(img)

    # Draw time at top-left
    draw.text((5, 5), time_str, font=font_12, fill=0)

    # Draw sensor ID at top-right
    id_text = f"ID {sensor_id}"
    w_id, h_id = font_12.getsize(id_text)
    draw.text((epd.height - w_id - 5, 5), id_text, font=font_12, fill=0)

    # Draw O₂ reading centered below
    w_o2, h_o2 = font_24.getsize(o2_str)
    x_o2 = (epd.height - w_o2) // 2
    y_o2 = (epd.width - h_o2) // 2 - 10
    draw.text((x_o2, y_o2), o2_str, font=font_24, fill=0)

    # Draw RH at bottom-left
    draw.text((5, epd.width - 20), rh_str, font=font_12, fill=0)

    # Draw Temp at bottom-right
    w_temp, h_temp = font_12.getsize(temp_str)
    draw.text((epd.height - w_temp - 5, epd.width - 20), temp_str, font=font_12, fill=0)

    # Send to display using partial update for speed
    epd.displayPartial(epd.getbuffer(img))

# =======================
# Main monitoring loop
# =======================
def monitor():
    global dev, connected

    base = os.path.dirname(__file__)
    log_path  = os.path.join(base, f"O2 sensor {sensor_id} log.csv")
    alog_path = os.path.join(base, f"O2 sensor {sensor_id} alarm log.csv")

    # Ensure log files exist
    if not os.path.isfile(log_path):
        with open(log_path, "w", newline="") as f:
            csv.writer(f).writerow(["Date & Time", "Sensor", "O2%", "Temp", "RH"])
    if not os.path.isfile(alog_path):
        with open(alog_path, "w", newline="") as f:
            csv.writer(f).writerow(["Sensor", "Start", "End", "Duration", "MaxDev", "Recipients"])

    dev = PASCOBLEDevice()

    # Step 1: Connect loop
    while True:
        try:
            dev.connect_by_id(sensor_id)
            print(f"Connected to sensor {sensor_id}")

            # Step 2: Read initial values, log, log “Connected” event, send initiation email
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
                    f"{o2_init:.1f}", f"{tmp_init:.1f}", f"{rh_init:.1f}"
                ])

            # Log “Connected” event
            with open(log_path, "a", newline="") as f:
                csv.writer(f).writerow([ts_full, sensor_id, "Connected", "", ""])

            # Send “initiated” email
            init_subject = f"O2 sensor {sensor_id} initiated"
            init_body = (
                f"The O₂ sensor {sensor_id} was initiated at {ts_full}.\n\n"
                f"Initial readings:\n"
                f"• O₂: {o2_init:.1f}%\n"
                f"• Temperature: {tmp_init:.1f}°C\n"
                f"• Humidity: {rh_init:.1f}%\n\n"
                f"A copy of the current log is attached."
            )
            send_email(init_subject, init_body, [log_path])
            print(f"Initiation email sent at {ts_full}")

            connected = True
            break

        except Exception as e:
            print(f"Connection failed: {e}. Retrying in 5 s…")
            time.sleep(5)

    # Main loop: read, print, update e-ink, alarms, periodic logging
    alarm = False
    start = None
    deviated = []
    last_alarm = 0
    last_log = time.time()
    last_daily_date = None

    # Initial e-ink update with placeholders
    update_eink("--:--", "O₂: --.-%", "RH: --.-%", "Temp: --.-°C")

    while True:
        # Read data; on failure, reconnect
        try:
            data = dev.read_data_list(["OxygenGasConcentration", "Temperature", "RelativeHumidity"])
        except Exception as e:
            print(f"Read error: {e}. Reconnecting…")
            try:
                dev.disconnect()
            except:
                pass
            time.sleep(1)
            while True:
                try:
                    dev.connect_by_id(sensor_id)
                    print(f"Reconnected to sensor {sensor_id}")
                    break
                except Exception as e2:
                    print(f"Reconnection failed: {e2}. Retrying in 5 s…")
                    time.sleep(5)
            continue

        # Extract values
        o2  = data["OxygenGasConcentration"] + o2_corr
        tmp = data["Temperature"]
        rh  = data["RelativeHumidity"]
        dt_full = datetime.now()
        ts_full = dt_full.strftime("%Y-%m-%d %H:%M:%S")
        ts = ts_full[11:16]  # HH:MM

        # Print to console
        print(f"{ts_full} | O₂: {o2:.1f}% | Temp: {tmp:.1f}°C | RH: {rh:.1f}%")

        # Update e-ink display (partial update)
        o2_str   = f"O₂: {o2:.1f}%"
        rh_str   = f"RH: {rh:.1f}%"
        temp_str = f"Temp: {tmp:.1f}°C"
        update_eink(ts, o2_str, rh_str, temp_str)

        # Alarm logic
        deviation = abs(o2 - o2_ref)
        if deviation > o2_thr:
            subj = f"ALARM - significant O₂ change in Sensor {sensor_id}"
            body = (
                f"O₂ changed more than {o2_thr:.1f}% from reference {o2_ref:.1f}% at {ts_full}.\n"
                f"Current values:\n"
                f"• O₂: {o2:.1f}%\n"
                f"• Temp: {tmp:.1f}°C\n"
                f"• Humidity: {rh:.1f}%"
            )
            if not alarm:
                alarm = True
                start = datetime.now()
                deviated = [o2]

                # Log values before sending alarm email
                with open(log_path, "a", newline="") as f:
                    csv.writer(f).writerow([ts_full, sensor_id, f"{o2:.1f}", f"{tmp:.1f}", f"{rh:.1f}"])

                # Log “Alarm triggered” event
                with open(log_path, "a", newline="") as f:
                    csv.writer(f).writerow([ts_full, sensor_id, "Alarm triggered", "", ""])

                send_email(subj, body, [log_path])
                print(f"Alarm email sent at {ts_full}")
                last_alarm = time.time()
            else:
                deviated.append(o2)
                if time.time() - last_alarm >= logtime_alarm:
                    # Log values before repeat alarm email
                    with open(log_path, "a", newline="") as f:
                        csv.writer(f).writerow([ts_full, sensor_id, f"{o2:.1f}", f"{tmp:.1f}", f"{rh:.1f}"])
                    send_email(subj, body, [log_path])
                    print(f"Repeat alarm email sent at {ts_full}")
                    last_alarm = time.time()
        else:
            if alarm:
                end = datetime.now()
                dur = end - start
                maxd = max(deviated, key=lambda x: abs(x - o2_ref))

                # Log values before restoration email
                with open(log_path, "a", newline="") as f:
                    csv.writer(f).writerow([ts_full, sensor_id, f"{o2:.1f}", f"{tmp:.1f}", f"{rh:.1f}"])

                # Log “Alarm deactivated” event
                with open(log_path, "a", newline="") as f:
                    csv.writer(f).writerow([ts_full, sensor_id, "Alarm deactivated", "", ""])

                with open(alog_path, "a", newline="") as f:
                    csv.writer(f).writerow([
                        sensor_id,
                        start.strftime("%Y-%m-%d %H:%M:%S"),
                        end.strftime("%Y-%m-%d %H:%M:%S"),
                        str(dur).split(".")[0],
                        f"{maxd:.2f}",
                        ",".join(recips),
                    ])
                subj = f"O₂ level restored for {sensor_id}"
                body = (
                    f"O₂ level returned to within ±{o2_thr:.1f}% of reference {o2_ref:.1f}% at {ts_full}.\n"
                    f"Current values:\n"
                    f"• O₂: {o2:.1f}%\n"
                    f"• Temp: {tmp:.1f}°C\n"
                    f"• Humidity: {rh:.1f}%\n"
                    f"Alarm Duration: {str(dur).split('.')[0]}"
                )
                send_email(subj, body, [log_path, alog_path])
                print(f"Restoration email sent at {ts_full}")
                alarm = False

        # Periodic logging: use intervals from config
        interval = logtime_alarm if alarm else logtime
        if time.time() - last_log >= interval:
            with open(log_path, "a", newline="") as f:
                csv.writer(f).writerow([ts_full, sensor_id, f"{o2:.1f}", f"{tmp:.1f}", f"{rh:.1f}"])
            last_log = time.time()

        # Daily summary at 23:59
        if dt_full.hour == 23 and dt_full.minute == 59:
            today = date.today().strftime("%Y-%m-%d")
            if last_daily_date != today:
                daily_subject = f"O2 sensor {sensor_id} - {today} daily log"
                daily_body = (
                    f"Attached is the daily log for {today} from O₂ sensor {sensor_id}.\n\n"
                    f"Best regards,\nO₂ Monitoring Script"
                )
                send_email(daily_subject, daily_body, [log_path])
                print(f"Daily log email sent at {ts_full}")
                last_daily_date = today

        time.sleep(2)

# Start monitor thread (non-blocking)
threading.Thread(target=monitor, daemon=True).start()

# Keep script alive (no Tkinter mainloop needed)
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    safe_disconnect()
    sys.exit(0)
