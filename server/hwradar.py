"""Streams radar contacts to physical hardware (ESP32 LED-ring radar, TFT, servo arm...) at 20 Hz.

One UTF-8 line per packet (UDP broadcast and/or USB serial), well under 250 bytes:

    NS1,<mode>,<hp>,<armor>|<bearing>,<dist>,<type>;<bearing>,<dist>,<type>;...

    mode     a = attract, p = playing, r = results, f = free play
    bearing  degrees CLOCKWISE from straight ahead (0..359) - heading-up, same as the phone radar
    dist     metres, one decimal
    type     E = enemy, P = armor plate
"""
import math
import socket

import config as C
from net import lan_ip


class HwRadar:
    MAX_BLIPS = 14

    def __init__(self):
        host = C.HW_RADAR_HOST
        if host == "auto":                               # x.y.z.255 of the Wi-Fi the PC is on
            host = lan_ip().rsplit(".", 1)[0] + ".255"
        self.addr = (host, C.HW_RADAR_PORT)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.ser = None
        if C.HW_RADAR_SERIAL:
            try:
                import serial                            # pip install pyserial (only for the USB option)
                self.ser = serial.Serial(C.HW_RADAR_SERIAL, 115200, timeout=0, write_timeout=0)
            except Exception as e:
                print(f"[hw] serial {C.HW_RADAR_SERIAL} unavailable ({e})")
        self.t = 0.0
        print(f"[hw] radar bridge -> UDP {self.addr[0]}:{self.addr[1]}"
              + (f" + serial {C.HW_RADAR_SERIAL}" if self.ser else ""))

    def packet(self, g):
        hr = math.radians(g.h)
        ch, sh = math.cos(hr), math.sin(hr)
        blips = []
        for kind, items in (("E", ((c["x"], c["y"]) for c in g.contacts.values())),
                            ("P", ((p.x, p.y) for p in g.plates))):
            for x, y in items:
                dx, dy = x - g.px, y - g.py
                right, fwd = dx * ch + dy * sh, -dx * sh + dy * ch
                blips.append((math.degrees(math.atan2(right, fwd)) % 360.0, min(99.9, math.hypot(dx, dy)), kind))
        blips.sort(key=lambda b: b[1])
        body = ";".join(f"{b:.0f},{d:.1f},{k}" for b, d, k in blips[:self.MAX_BLIPS])
        return f"NS1,{g.show.mode[0]},{int(g.hp)},{int(g.armor)}|{body}"

    def tick(self, dt, g):
        self.t += dt
        if self.t < 1 / 20:
            return
        self.t = 0.0
        pkt = self.packet(g)
        try:
            self.sock.sendto(pkt.encode(), self.addr)
        except OSError:
            pass
        if self.ser:
            try:
                self.ser.write((pkt + "\n").encode())
            except Exception:
                pass
