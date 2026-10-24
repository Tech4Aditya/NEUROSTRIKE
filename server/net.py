"""WebSocket link to the phone. Runs its own asyncio loop in a daemon thread."""
import asyncio
import json
import socket
import threading
import time

import websockets


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class InputState:
    """Latest phone input. Aim deltas accumulate until the game consumes them,
    so touch + gyro can never fight each other — they simply add."""

    STALE = 0.5

    def __init__(self):
        self.lock = threading.Lock()
        self.jx = self.jy = 0.0
        self.fire = False
        self.yaw = self.pitch = 0.0
        self.reload = self.tac = False
        self.last_rx = 0.0

    def update(self, m):
        with self.lock:
            self.jx = max(-1.0, min(1.0, float(m.get("jx", 0))))
            self.jy = max(-1.0, min(1.0, float(m.get("jy", 0))))
            self.fire = bool(m.get("fire", False))
            self.yaw += float(m.get("dyaw", 0))
            self.pitch += float(m.get("dpitch", 0))
            self.reload = self.reload or bool(m.get("reload", False))
            self.tac = self.tac or bool(m.get("tac", False))
            self.last_rx = time.time()

    def consume(self):
        """-> (jx, jy, fire, dyaw, dpitch, reload, tac, connected)"""
        with self.lock:
            live = (time.time() - self.last_rx) < self.STALE
            out = (self.jx, self.jy, self.fire, self.yaw, self.pitch, self.reload, self.tac)
            self.yaw = self.pitch = 0.0
            self.reload = self.tac = False
        if not live:
            return 0.0, 0.0, False, out[3], out[4], False, False, False
        return (*out, True)


class PhoneLink(threading.Thread):
    def __init__(self, host, port, hz):
        super().__init__(daemon=True, name="phone-link")
        self.host, self.port, self.hz = host, port, hz
        self.input = InputState()
        self.clients = set()
        self._json = None

    def publish(self, state: dict):
        self._json = json.dumps(state, separators=(",", ":"))

    def run(self):
        try:
            asyncio.run(self._main())
        except OSError as e:
            print(f"[net] cannot listen on {self.host}:{self.port} -> {e}")

    async def _handler(self, ws, *_):
        self.clients.add(ws)
        try:                                   # disable Nagle: small input packets must not wait to be batched
            sock = ws.transport.get_extra_info("socket")
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass
        print(f"[net] phone connected ({len(self.clients)} client(s))")
        try:
            async for raw in ws:
                try:
                    m = json.loads(raw)
                except ValueError:
                    continue
                kind = m.get("t")
                if kind == "input":
                    self.input.update(m)
                elif kind == "ping":
                    await ws.send(json.dumps({"t": "pong", "ts": m.get("ts")}))
        except websockets.ConnectionClosed:
            pass
        finally:
            self.clients.discard(ws)
            print("[net] phone disconnected")

    @staticmethod
    async def _send(ws, msg):
        try:
            await ws.send(msg)
        except Exception:
            pass

    async def _broadcast(self):
        period = 1.0 / self.hz
        while True:
            msg = self._json
            if msg and self.clients:
                await asyncio.gather(*(self._send(c, msg) for c in list(self.clients)))
            await asyncio.sleep(period)

    async def _main(self):
        async with websockets.serve(self._handler, self.host, self.port, ping_interval=None):
            await self._broadcast()
