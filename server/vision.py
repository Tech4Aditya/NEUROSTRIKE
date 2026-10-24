"""Detection pipeline: runs in its own thread so inference never blocks the game loop.

Detectors
  * YoloDetector  — Ultralytics YOLO with your trained weights (models/enemy.pt)
  * ColorDetector — zero-setup fallback (HSV segmentation of the enemy colour)
A tiny centroid tracker gives every target a stable ID across frames.
"""
import math
import threading
import time

import cv2
import numpy as np

import config as C


class ColorDetector:
    name = "COLOR"

    def __call__(self, bgr):
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        hue, sat, val = cv2.split(hsv)
        mask = (((hue >= 165) | (hue <= 6)) & (sat > 110) & (val > 110)).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
        H, W = mask.shape
        out = []
        for i in range(1, n):
            x, y, w, h, area = stats[i]
            if area < 40 or h < 8:
                continue
            fill = area / float(w * h)
            out.append(dict(x1=x / W, y1=y / H, x2=(x + w) / W, y2=(y + h) / H,
                            conf=float(min(0.99, 0.5 + 0.5 * fill))))
        return out


class YoloDetector:
    name = "YOLO"

    def __init__(self, weights):
        import os
        import torch
        from ultralytics import YOLO  # imported lazily: optional dependency
        torch.set_num_threads(max(1, (os.cpu_count() or 4) // 2))   # leave cores for the game
        self.half = torch.cuda.is_available()
        self.model = YOLO(str(weights))

    def __call__(self, bgr):
        res = self.model.predict(bgr, imgsz=640, conf=C.YOLO_CONF, verbose=False, half=self.half)[0]
        H, W = bgr.shape[:2]
        out = []
        for b in res.boxes:
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            out.append(dict(x1=x1 / W, y1=y1 / H, x2=x2 / W, y2=y2 / H, conf=float(b.conf[0])))
        return out


def build_detector(mode="auto"):
    have = C.YOLO_WEIGHTS.exists()
    if mode in ("auto", "yolo") and have:
        try:
            det = YoloDetector(C.YOLO_WEIGHTS)
            print(f"[vision] YOLO loaded: {C.YOLO_WEIGHTS.name}")
            return det
        except Exception as e:  # missing ultralytics, bad weights...
            print(f"[vision] YOLO unavailable ({e}); falling back to colour detector")
    elif mode == "yolo":
        print("[vision] models/enemy.pt not found — see README 'Train YOLO'. Using colour detector.")
    elif mode == "auto":
        print("[vision] no trained weights yet -> colour detector (press F9 in-game to record a dataset)")
    return ColorDetector()


class Tracker:
    def __init__(self, max_dist=0.15, max_miss=6):
        self.max_dist, self.max_miss = max_dist, max_miss
        self.tracks, self.next_id = {}, 1

    def update(self, dets):
        cents = [((d["x1"] + d["x2"]) / 2, (d["y1"] + d["y2"]) / 2) for d in dets]
        pairs = sorted((math.hypot(c[0] - t["cx"], c[1] - t["cy"]), i, tid)
                       for i, c in enumerate(cents) for tid, t in self.tracks.items())
        used_d, touched = set(), set()
        for dist, i, tid in pairs:
            if dist > self.max_dist:
                break
            if i in used_d or tid in touched:
                continue
            used_d.add(i)
            touched.add(tid)
            dets[i]["id"] = tid
            self.tracks[tid].update(cx=cents[i][0], cy=cents[i][1], miss=0)
        for i, d in enumerate(dets):
            if i not in used_d:
                tid = self.next_id
                self.next_id += 1
                self.tracks[tid] = dict(cx=cents[i][0], cy=cents[i][1], miss=0)
                d["id"] = tid
                touched.add(tid)
        for tid in list(self.tracks):
            if tid not in touched:
                self.tracks[tid]["miss"] += 1
                if self.tracks[tid]["miss"] > self.max_miss:
                    del self.tracks[tid]
        return dets


class VisionWorker(threading.Thread):
    def __init__(self, detector):
        super().__init__(daemon=True, name="vision")
        self.detector, self.tracker = detector, Tracker()
        self._cv = threading.Condition()
        self._slot = None
        self._result = None
        self._seq = 0

    @property
    def name(self):
        return self.detector.name

    def submit(self, frame, meta):
        """Single-slot mailbox: if the detector is busy the stale frame is dropped."""
        with self._cv:
            self._slot = (frame, meta)
            self._cv.notify()

    def latest(self):
        return self._result

    def run(self):
        while True:
            with self._cv:
                while self._slot is None:
                    self._cv.wait()
                frame, meta = self._slot
                self._slot = None
            t0 = time.perf_counter()
            try:
                dets = self.detector(frame)
            except Exception as e:
                print(f"[vision] inference error: {e}")
                dets = []
            dets = self.tracker.update(dets)
            self._seq += 1
            self._result = dict(dets=dets, meta=meta, seq=self._seq,
                                ms=(time.perf_counter() - t0) * 1000.0)
