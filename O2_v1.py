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

# ─── Patch Bleak WinRT scanner exceptions (unchanged) ───
try:
    import bleak.backends.winrt.scanner as _scanner_mod
    _orig = _scanner_mod.BleakScannerWinRT._stopped_handler
    def _safe(self, sender, args):
        try:
            return _orig(self, sender, args)
        except:
            return None
    _scanner_mod.BleakScannerWinRT._stopped_handler = _safe
except ImportError:
    pass

from pasco import PASCOBLEDevice
import tkinter as tk
from tkinter import StringVar

# =======================
# Module‐level device reference, initially None
# =======================
dev = None

# =======================
# Cleanup function: always attempt to disconnect the sensor
# =======================
def safe_disconnect():
    global dev
    try:
        if dev is not None:
            dev.disconnect()
            print("Sensor disconnected cleanly.")
    except Exception as e:
        print(f"Error while disconnecting sensor: {e}")

# Register safe_disconnect to be called on normal interpreter exit
atexit.register(safe_disconnect)

# Also catch SIGINT (Ctrl+C) and SIGTERM so we can disconnect before exiting
def _signal_handler(signum, frame):
    print(f"Received signal {signum}; disconnecting sensor and exiting.")
    safe_disconnect()
    sys.exit(0)

signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)

# =======================
# Helper: send email (unchanged)
# =======================
def send_email(subject, body, attachments=[]):
    msg = EmailMessage()
    msg['Subject'], msg['From'], msg['To'] = subject, sender, ', '.join(recips)
    msg.set_content(body)
    for p in attachments:
        try:
            with open(p,'rb') as f:
                data = f.read()
            msg.add_attachment(
                data,
                maintype='application',
                subtype='octet-stream',
                filename=os.path.basename(p)
            )
        except FileNotFoundError:
            print("Missing attachment:", p)
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(sender, pw)
            s.send_message(msg)
    except Exception as e:
        print(f"Email failed '{subject}': {e}")

# =======================
# Load configuration (unchanged)
# =======================
cfg = configparser.ConfigParser()
cfg.read('O2_sensor.cfg')
sensor_id = cfg['SensorSettings']['sensor_id'].strip("'\"")
o2_corr    = float(cfg['SensorSettings']['O2_sensor_cf'])
o2_ref     = float(cfg['SensorSettings']['O2_ref'])
o2_thr     = float(cfg['SensorSettings']['O2_threshold'])
recips     = [e.strip() for e in cfg['Email']['recipients'].split(',')]
sender     = cfg['Email']['sender_email']
pw         = cfg['Email']['app_password']

# =======================
# GUI setup (unchanged)
# =======================
root = tk.Tk()
root.title("O₂ Monitor")
root.geometry("250x122")
root.attributes("-topmost", True)
root.resizable(False, False)

time_var = StringVar(value="--:--")
o2_var   = StringVar(value="O₂: --.-%")
rh_var   = StringVar(value="--.-%")
temp_var = StringVar(value="--.-°C")

lbl_time      = tk.Label(root, textvariable=time_var,      font=("DS-Digital", 10))
lbl_bt        = tk.Label(root, text=f"\u2387 {sensor_id}", font=("Arial", 10))
lbl_o2        = tk.Label(root, textvariable=o2_var,        font=("DS-Digital", 24, "bold"))
lbl_rh_icon   = tk.Label(root, text="💧",                  font=("Arial", 13))
lbl_rh        = tk.Label(root, textvariable=rh_var,        font=("DS-Digital", 11))
lbl_temp_icon = tk.Label(root, text="🌡",                  font=("Arial", 13))
lbl_temp      = tk.Label(root, textvariable=temp_var,      font=("DS-Digital", 11))

root.grid_rowconfigure(1, weight=1)
root.grid_columnconfigure(1, weight=1)

lbl_time.grid(     row=0, column=0, sticky="w")
lbl_bt.grid(       row=0, column=2, sticky="e")
lbl_o2.grid(       row=1, column=0, columnspan=3)
lbl_rh_icon.grid(  row=2, column=0, sticky="w")
lbl_rh.grid(       row=2, column=1, sticky="w")
lbl_temp_icon.grid(row=2, column=1, sticky="e")
lbl_temp.grid(     row=2, column=2, sticky="e")

# =======================
# Main monitoring loop
# =======================
def monitor():
    global dev

    # Prepare file paths
    base = os.path.dirname(__file__)
    log  = os.path.join(base, f"O2 sensor {sensor_id} log.csv")
    alog = os.path.join(base, f"O2 sensor {sensor_id} alarm log.csv")

    # Initialize logs if they don't exist
    if not os.path.isfile(log):
        with open(log, "w", newline='') as f:
            csv.writer(f).writerow(['Date & Time','Sensor','O2%','Temp','RH'])
    if not os.path.isfile(alog):
        with open(alog, "w", newline='') as f:
            csv.writer(f).writerow(['Sensor','Start','End','Duration','MaxDev','Recipients'])

    dev = PASCOBLEDevice()

    # Attempt to connect (retry until successful)
    while True:
        try:
            dev.connect_by_id(sensor_id)
            print(f"Connected to sensor {sensor_id}")
            # ─── New: read sensor once, log it, then send initiation email ───
            try:
                data_init = dev.read_data_list(['OxygenGasConcentration','Temperature','RelativeHumidity'])
                o2_init  = data_init['OxygenGasConcentration'] + o2_corr
                tmp_init = data_init['Temperature']
                rh_init  = data_init['RelativeHumidity']
            except Exception as e:
                print(f"Initial read error: {e}. Using placeholders for initial values.")
                o2_init, tmp_init, rh_init = (o2_ref, 0.0, 0.0)

            ts_full = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Log initial values (unchanged)
            with open(log, "a", newline='') as f:
                csv.writer(f).writerow([
                    ts_full,
                    sensor_id,
                    f"{o2_init:.1f}",
                    f"{tmp_init:.1f}",
                    f"{rh_init:.1f}"
                ])
            # Construct initiation email with updated subject/body
            init_subject = f"O2 sensor {sensor_id} initiated"
            init_body = (
                f"The O₂ sensor {sensor_id} was initiated at {ts_full}.\n\n"
                f"Initial readings:\n"
                f"• O₂: {o2_init:.1f}%\n"
                f"• Temperature: {tmp_init:.1f}°C\n"
                f"• Humidity: {rh_init:.1f}%\n\n"
                f"A copy of the current log is attached."
            )
            send_email(init_subject, init_body, [log])
            print(f"Initiation email sent at {ts_full}")
            break
        except Exception as e:
            print(f"Connection failed: {e}. Retrying in 5 s...")
            time.sleep(5)

    alarm = False
    start = None
    deviated = []
    last_alarm = 0
    last_log = time.time()
    last_daily_date = None

    while True:
        # ─── Read data; if it fails, try reconnect ───
        try:
            data = dev.read_data_list(['OxygenGasConcentration','Temperature','RelativeHumidity'])
        except Exception as e:
            print(f"Read error: {e}. Reconnecting...")
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
                    print(f"Reconnection failed: {e2}. Retrying in 5 s...")
                    time.sleep(5)
            continue

        # ─── Extract sensor values ───
        o2  = data['OxygenGasConcentration'] + o2_corr
        tmp = data['Temperature']
        rh  = data['RelativeHumidity']
        dt_full = datetime.now()
        ts_full = dt_full.strftime("%Y-%m-%d %H:%M:%S")
        ts = ts_full[11:16]  # HH:MM

        # ─── Update GUI every ~2 s ───
        root.after(0, lambda: time_var.set(ts))
        root.after(0, lambda: o2_var.set(f"O₂: {o2:.1f}%"))
        root.after(0, lambda: rh_var.set(f"{rh:.1f}%"))
        root.after(0, lambda: temp_var.set(f"{tmp:.1f}°C"))

        # ─── Print to console every ~2 s ───
        print(f"{ts_full} | O₂: {o2:.1f}% | Temp: {tmp:.1f}°C | RH: {rh:.1f}%")

        # ─── Alarm logic (unchanged) ───
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
                # Log immediately before sending alarm email (unchanged)
                with open(log, "a", newline='') as f:
                    csv.writer(f).writerow([ts_full, sensor_id, f"{o2:.1f}", f"{tmp:.1f}", f"{rh:.1f}"])
                send_email(subj, body, [log])
                print(f"Alarm email sent at {ts_full}")
                last_alarm = time.time()
            else:
                deviated.append(o2)
                if time.time() - last_alarm >= 1800:
                    # Log immediately before sending repeat alarm email (unchanged)
                    with open(log, "a", newline='') as f:
                        csv.writer(f).writerow([ts_full, sensor_id, f"{o2:.1f}", f"{tmp:.1f}", f"{rh:.1f}"])
                    send_email(subj, body, [log])
                    print(f"Repeat alarm email sent at {ts_full}")
                    last_alarm = time.time()
        else:
            if alarm:
                end = datetime.now()
                dur = end - start
                maxd = max(deviated, key=lambda x: abs(x - o2_ref))
                # Log immediately before sending restoration email (unchanged)
                with open(log, "a", newline='') as f:
                    csv.writer(f).writerow([ts_full, sensor_id, f"{o2:.1f}", f"{tmp:.1f}", f"{rh:.1f}"])
                with open(alog, "a", newline='') as f:
                    csv.writer(f).writerow([
                        sensor_id,
                        start.strftime("%Y-%m-%d %H:%M:%S"),
                        end.strftime("%Y-%m-%d %H:%M:%S"),
                        str(dur).split('.')[0],
                        f"{maxd:.2f}",
                        ','.join(recips)
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
                send_email(subj, body, [log, alog])
                print(f"Restoration email sent at {ts_full}")
                alarm = False

        # ─── Periodic logging: 30 min if no alarm; 10 min if alarm active ───
        interval = 600 if alarm else 1800  # 600 s = 10 min, 1800 s = 30 min
        if time.time() - last_log >= interval:
            with open(log, "a", newline='') as f:
                csv.writer(f).writerow([ts_full, sensor_id, f"{o2:.1f}", f"{tmp:.1f}", f"{rh:.1f}"])
            last_log = time.time()

        # ─── Daily summary at 23:59 (unchanged subject format) ───
        if dt_full.hour == 23 and dt_full.minute == 59:
            today = date.today().strftime("%Y-%m-%d")
            if last_daily_date != today:
                daily_subject = f"O2 sensor {sensor_id} - {today} daily log"
                daily_body = (
                    f"Attached is the daily log for {today} from O₂ sensor {sensor_id}.\n\n"
                    f"Best regards,\nO₂ Monitoring Script"
                )
                send_email(daily_subject, daily_body, [log])
                print(f"Daily log email sent at {ts_full}")
                last_daily_date = today

        time.sleep(2)

# Start the monitoring thread (non‐blocking)
threading.Thread(target=monitor, daemon=True).start()

# Run the Tkinter event loop; use try/finally to ensure cleanup
try:
    root.mainloop()
finally:
    # In case mainloop exits unexpectedly, ensure the sensor is disconnected
    safe_disconnect()
