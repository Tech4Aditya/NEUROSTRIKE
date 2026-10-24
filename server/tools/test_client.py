"""Fake phone for latency/stability testing without the Android app.
    python tools/test_client.py [host] [seconds]"""
import asyncio
import json
import math
import statistics
import sys
import time

import websockets


async def main(host="127.0.0.1", secs=10.0):
    rtts, states = [], 0
    async with websockets.connect(f"ws://{host}:8765") as ws:
        async def rx():
            nonlocal states
            async for raw in ws:
                m = json.loads(raw)
                if m["t"] == "state":
                    states += 1
                elif m["t"] == "pong":
                    rtts.append((time.perf_counter_ns() - m["ts"]) / 1e6)
        task = asyncio.create_task(rx())
        t0, i = time.time(), 0
        while time.time() - t0 < secs:
            t = time.time() - t0
            await ws.send(json.dumps({"t": "input", "jx": round(math.sin(t), 3), "jy": 1.0,
                                      "dyaw": 0.8 * math.cos(t), "dpitch": 0.0, "fire": i % 30 < 5}))
            if i % 60 == 0:
                await ws.send(json.dumps({"t": "ping", "ts": time.perf_counter_ns()}))
            i += 1
            await asyncio.sleep(1 / 60)
        task.cancel()
    print(f"sent {i} inputs, got {states} states ({states / secs:.1f}/s)")
    if rtts:
        print(f"RTT ms  avg {statistics.mean(rtts):.1f}  max {max(rtts):.1f}  n={len(rtts)}")


if __name__ == "__main__":
    asyncio.run(main(*(sys.argv[1:2] or ["127.0.0.1"]), float(sys.argv[2]) if len(sys.argv) > 2 else 10.0))
