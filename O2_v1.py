
import time
import os
import csv
import configparser
import smtplib
import threading
from datetime import datetime
from email.message import EmailMessage

# Patch Bleak WinRT scanner exceptions
try:
    import bleak.backends.winrt.scanner as _scanner_mod
    _orig = _scanner_mod.BleakScannerWinRT._stopped_handler
    def _safe(self, sender, args):
        try: return _orig(self, sender, args)
        except: return None
    _scanner_mod.BleakScannerWinRT._stopped_handler = _safe
except ImportError:
    pass

from pasco import PASCOBLEDevice
import tkinter as tk
from tkinter import StringVar

# Load configuration
cfg = configparser.ConfigParser()
cfg.read('O2_sensor.cfg')
sensor_id = cfg['SensorSettings']['sensor_id'].strip("'\"")
o2_corr = float(cfg['SensorSettings']['O2_sensor_cf'])
o2_ref = float(cfg['SensorSettings']['O2_ref'])
o2_thr = float(cfg['SensorSettings']['O2_threshold'])
recips = [e.strip() for e in cfg['Email']['recipients'].split(',')]
sender = cfg['Email']['sender_email']
pw = cfg['Email']['app_password']

def send_email(subject, body, attachments=[]):
    msg = EmailMessage()
    msg['Subject'], msg['From'], msg['To'] = subject, sender, ', '.join(recips)
    msg.set_content(body)
    for p in attachments:
        try:
            with open(p,'rb') as f: data=f.read()
            msg.add_attachment(data, maintype='application', subtype='octet-stream', filename=os.path.basename(p))
        except FileNotFoundError:
            print("Missing attachment:", p)
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com',465) as s:
            s.login(sender,pw); s.send_message(msg)
    except Exception as e:
        print(f"Email failed '{subject}':", e)

# GUI setup
root = tk.Tk()
root.title("O₂ Monitor")
root.geometry("250x122")
root.attributes("-topmost", True)
root.resizable(False, False)

# Variables
time_var = StringVar(value="--:--")
o2_var   = StringVar(value="O₂: --.-%")
rh_var   = StringVar(value="--.-%")
temp_var = StringVar(value="--.-°C")
bt_var   = StringVar(value="")

# Widgets
lbl_time      = tk.Label(root, textvariable=time_var,      font=("DS-Digital", 10))
lbl_bt        = tk.Label(root, text=f"\u2387 {sensor_id}", font=("Arial", 10))
lbl_o2        = tk.Label(root, textvariable=o2_var,        font=("DS-Digital", 24, "bold"))
lbl_rh_icon   = tk.Label(root, text="💧",                  font=("Arial", 13))
lbl_rh        = tk.Label(root, textvariable=rh_var,        font=("DS-Digital", 11))
lbl_temp_icon = tk.Label(root, text="🌡",                  font=("Arial", 13))
lbl_temp      = tk.Label(root, textvariable=temp_var,      font=("DS-Digital", 11))

# Layout with correct grid parameters
root.grid_rowconfigure(1, weight=1)
root.grid_columnconfigure(1, weight=1)

lbl_time.grid(     row=0, column=0, sticky="w")
lbl_bt.grid(       row=0, column=2, sticky="e")
lbl_o2.grid(       row=1, column=0, columnspan=3)
lbl_rh_icon.grid(  row=2, column=0, sticky="w")
lbl_rh.grid(       row=2, column=1, sticky="w")
lbl_temp_icon.grid(row=2, column=1, sticky="e")
lbl_temp.grid(     row=2, column=2, sticky="e")

def monitor():
    dev = PASCOBLEDevice()
    # connect
    while True:
        try:
            dev.connect_by_id(sensor_id)
            break
        except Exception as e:
            print(f"Connection failed: {e}. Retrying in 5s...")
            time.sleep(5)

    # file paths
    base = os.path.dirname(__file__)
    log  = os.path.join(base, f"O2 sensor {sensor_id} log.csv")
    alog = os.path.join(base, f"O2 sensor {sensor_id} alarm log.csv")
    # initialize logs
    if not os.path.isfile(log):
        with open(log, "w", newline='') as f: csv.writer(f).writerow(['Date & Time','Sensor','O2%','Temp','RH'])
    if not os.path.isfile(alog):
        with open(alog, "w", newline='') as f: csv.writer(f).writerow(['Sensor','Start','End','Duration','MaxDev','Recipients'])

    alarm=False; start=None; deviated=[]
    last_alarm=0; last_log=time.time()

    while True:
        try:
            data = dev.read_data_list(['OxygenGasConcentration','Temperature','RelativeHumidity'])
        except Exception as e:
            print(f"Read error: {e}. Reconnecting...")
            try: dev.disconnect()
            except: pass
            time.sleep(1)
            continue

        # sensor values
        o2  = data['OxygenGasConcentration'] + o2_corr
        tmp = data['Temperature']
        rh  = data['RelativeHumidity']
        ts_full = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ts = ts_full[11:16]  # HH:MM

        # update GUI
        root.after(0, lambda: time_var.set(ts))
        root.after(0, lambda: o2_var.set(f"O₂: {o2:.1f}%"))
        root.after(0, lambda: rh_var.set(f"{rh:.1f}%"))
        root.after(0, lambda: temp_var.set(f"{tmp:.1f}°C"))

        # print to console
        print(f"{ts_full} | O₂: {o2:.1f}% | Temp: {tmp:.1f}°C | RH: {rh:.1f}%")

        deviation = abs(o2 - o2_ref)
        if deviation > o2_thr:
            subj = f"ALARM - significant O2 change in Sensor {sensor_id}"
            body = (
                f"O₂ changed more than {o2_thr:.1f} from reference {o2_ref:.1f}% at {ts_full}.\n"
                f"Current values:\nO₂: {o2:.1f}%\nTemp: {tmp:.1f}°C\nHumidity: {rh:.1f}%"
            )
            if not alarm:
                alarm=True; start=datetime.now(); deviated=[o2]
                # log before email
                with open(log, "a", newline='') as f: csv.writer(f).writerow([ts_full, sensor_id, f"{o2:.1f}", f"{tmp:.1f}", f"{rh:.1f}"])
                send_email(subj, body, [log])
                print(f"Alarm email sent at {ts_full}")
                last_alarm=time.time()
            else:
                deviated.append(o2)
                if time.time()-last_alarm >= 1800:
                    with open(log, "a", newline='') as f: csv.writer(f).writerow([ts_full, sensor_id, f"{o2:.1f}", f"{tmp:.1f}", f"{rh:.1f}"])
                    send_email(subj, body, [log])
                    print(f"Repeat alarm email sent at {ts_full}")
                    last_alarm=time.time()
        else:
            if alarm:
                end = datetime.now(); dur = end - start
                maxd = max(deviated, key=lambda x: abs(x - o2_ref))
                with open(log, "a", newline='') as f: csv.writer(f).writerow([ts_full, sensor_id, f"{o2:.1f}", f"{tmp:.1f}", f"{rh:.1f}"])
                with open(alog, "a", newline='') as f:
                    csv.writer(f).writerow([
                        sensor_id,
                        start.strftime("%Y-%m-%d %H:%M:%S"),
                        end.strftime("%Y-%m-%d %H:%M:%S"),
                        str(dur).split('.')[0],
                        f"{maxd:.2f}",
                        ','.join(recips)
                    ])
                subj = f"O2 level restored for {sensor_id}"
                body = (
                    f"O₂ level returned to within ±{o2_thr:.1f} of reference {o2_ref:.1f}% at {ts_full}.\n"
                    f"Current values:\nO₂: {o2:.1f}%\nTemp: {tmp:.1f}°C\nHumidity: {rh:.1f}%\n"
                    f"Alarm Duration: {str(dur).split('.')[0]}"
                )
                send_email(subj, body, [log, alog])
                print(f"Restoration email sent at {ts_full}")
                alarm=False

        # periodic logging every 60s
        if time.time()-last_log >= 60:
            with open(log, "a", newline='') as f: csv.writer(f).writerow([ts_full, sensor_id, f"{o2:.1f}", f"{tmp:.1f}", f"{rh:.1f}"])
            last_log=time.time()

        time.sleep(2)

# start monitoring and GUI
threading.Thread(target=monitor, daemon=True).start()
root.mainloop()
