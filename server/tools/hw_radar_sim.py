"""Pretends to be the hardware radar: listens for the game's UDP packets and draws an ASCII radar.
Use it to check the network path before the ESP32 is wired up.
    python tools/hw_radar_sim.py [port]"""
import math
import socket
import sys
import time

port = int(sys.argv[1]) if len(sys.argv) > 1 else 4210
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("", port))
s.settimeout(1.0)
print(f"listening on UDP {port} ... start the game with:  python main.py --hw-radar")
last_draw, n, t0 = 0.0, 0, time.time()
R = 10
while True:
    try:
        data, addr = s.recvfrom(512)
    except socket.timeout:
        print("(no packets)"); continue
    n += 1
    line = data.decode(errors="replace").strip()
    if time.time() - last_draw > 0.25:
        last_draw = time.time()
        head, _, body = line.partition("|")
        _, mode, hp, armor = head.split(",")
        grid = [[" "] * (2 * R * 2 + 1) for _ in range(2 * R + 1)]
        for ring in (R // 3, 2 * R // 3, R):
            for a in range(0, 360, 6):
                x = int(round(R * 2 + ring * 2 * math.sin(math.radians(a)))); y = int(round(R - ring * math.cos(math.radians(a))))
                if 0 <= y < len(grid) and 0 <= x < len(grid[0]) and grid[y][x] == " ":
                    grid[y][x] = "."
        grid[R][R * 2] = "^"
        for b in filter(None, body.split(";")):
            ang, dist, kind = b.split(",")
            r = min(float(dist) / 30.0, 1.0) * R
            x = int(round(R * 2 + r * 2 * math.sin(math.radians(float(ang))))); y = int(round(R - r * math.cos(math.radians(float(ang)))))
            grid[y][x] = "E" if kind == "E" else "+"
        print("\033[2J\033[H" + "\n".join("".join(r) for r in grid))
        print(f"from {addr[0]} | mode {mode} hp {hp} armor {armor} | {n / (time.time() - t0):.1f} packets/s\n{line}")
