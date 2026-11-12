"""Procedural sound effects — no audio files shipped. WAVs are synthesised on first run
into server/sounds/ and loaded through Panda3D's audio manager."""
import wave
from pathlib import Path

import numpy as np
from panda3d.core import Filename

import config as C

SR = 44100


def _t(d):
    return np.arange(int(SR * d)) / SR


def _noise(n, seed):
    return np.random.default_rng(seed).standard_normal(n)


def _lp(x, hz):
    X = np.fft.rfft(x); X[np.fft.rfftfreq(len(x), 1 / SR) > hz] = 0
    return np.fft.irfft(X, len(x))


def _hp(x, hz):
    X = np.fft.rfft(x); X[np.fft.rfftfreq(len(x), 1 / SR) < hz] = 0
    return np.fft.irfft(X, len(x))


def _norm(x, peak=0.9):
    return x / (np.abs(x).max() + 1e-9) * peak


def _place(dst, snd, t0):
    i = int(t0 * SR)
    n = min(len(snd), len(dst) - i)
    if n > 0:
        dst[i:i + n] += snd[:n]


def _mix(*xs):
    out = np.zeros(max(len(x) for x in xs))
    for x in xs:
        out[:len(x)] += x
    return out


def _tick(freq, dur=0.04, gain=1.0):
    t = _t(dur)
    return gain * (np.sin(2 * np.pi * freq * t) * np.exp(-t * 150) +
                   0.6 * _hp(_noise(len(t), int(freq)), 3000) * np.exp(-t * 220))


def _thunk(freq=110, dur=0.12, gain=1.0):
    t = _t(dur)
    return gain * (np.sin(2 * np.pi * freq * t) * np.exp(-t * 38) +
                   0.5 * _lp(_noise(len(t), int(freq) + 7), 500) * np.exp(-t * 45))


def gunshot():
    t = _t(0.45); n = _noise(len(t), 1)
    crack = _hp(n, 1500) * np.exp(-t * 90)
    body = _lp(n, 2500) * np.exp(-t * 18)
    thump = np.sin(2 * np.pi * (55 + 90 * np.exp(-t * 30)) * t) * np.exp(-t * 14)
    tail = _lp(_noise(len(t), 2), 600) * np.exp(-t * 7) * 0.5
    return _norm(0.9 * crack + 0.8 * body + 1.2 * thump + tail, 0.95)


def reload_full():
    x = np.zeros(int(SR * 2.4))
    _place(x, _mix(_tick(2200, 0.05), 0.6 * _tick(1400, 0.05)), 0.15)      # mag release
    _place(x, _thunk(160, 0.10, 0.5), 0.30)                           # mag drops
    _place(x, _thunk(95, 0.14, 1.0), 1.05)                            # new mag seated
    _place(x, _mix(_tick(1800, 0.05), 0.5 * _tick(900, 0.06)), 1.55)       # bolt back
    _place(x, _mix(_thunk(130, 0.10, 0.9), _tick(2500, 0.03)), 1.90)       # bolt forward
    return _norm(x, 0.8)


def reload_tac():
    x = np.zeros(int(SR * 1.7))
    _place(x, _mix(_tick(2200, 0.05), 0.6 * _tick(1400, 0.05)), 0.10)
    _place(x, _thunk(160, 0.10, 0.4), 0.25)
    _place(x, _thunk(95, 0.14, 1.0), 0.95)
    _place(x, _tick(1500, 0.04), 1.25)
    return _norm(x, 0.8)


def click():
    return _norm(_mix(_tick(1300, 0.03), _tick(700, 0.03) * 0.5), 0.6)


def hit():
    t = _t(0.06)
    return _norm(np.sin(2 * np.pi * 1100 * t) * np.exp(-t * 90) + 0.3 * _hp(_noise(len(t), 3), 2500) * np.exp(-t * 120), 0.7)


def kill():
    t = _t(0.25)
    x = np.sin(2 * np.pi * (170 - 60 * t) * t) * np.exp(-t * 14) + 0.5 * _lp(_noise(len(t), 4), 900) * np.exp(-t * 20)
    return _norm(x, 0.85)


def hurt():
    t = _t(0.3)
    x = np.sin(2 * np.pi * 70 * t) * np.exp(-t * 12) + 0.7 * _lp(_noise(len(t), 5), 700) * np.exp(-t * 15)
    return _norm(x, 0.9)


def step():
    t = _t(0.14)
    return _norm(_lp(_noise(len(t), 6), 900) * np.exp(-t * 32) + 0.6 * np.sin(2 * np.pi * 70 * t) * np.exp(-t * 28), 0.6)


def enemy_steps():
    x = np.zeros(int(SR * 0.9))
    _place(x, step(), 0.0)
    _place(x, step() * 0.9, 0.45)
    return _norm(x, 0.8)


def whoosh():
    t = _t(0.7)
    env = np.sin(np.pi * t / 0.7) ** 2
    return _norm(_hp(_lp(_noise(len(t), 8), 3500), 250) * env, 0.6)


def ambience():
    d = 8.0
    t = _t(d)
    wind = _lp(_noise(len(t), 9), 450) * (0.65 + 0.35 * np.sin(2 * np.pi * t / d))
    hiss = _lp(_hp(_noise(len(t), 10), 800), 2000) * 0.18 * (0.5 + 0.5 * np.sin(2 * np.pi * 2 * t / d + 1))
    return _norm(wind + hiss, 0.5)           # FFT-filtered noise is periodic -> loops seamlessly


def plate_pickup():
    t = _t(0.30)
    sweep = np.sin(2 * np.pi * (800 + 2600 * t / 0.30) * t) * np.exp(-t * 9) * 0.5
    return _norm(_mix(sweep, _tick(3200, 0.05, 0.7)), 0.7)


def plate_apply():
    """velcro rip -> plate scrapes in -> clack -> lock thump -> shimmer (about 1.8 s)."""
    x = np.zeros(int(SR * 1.9))
    t = _t(0.45)
    rip = _hp(_noise(len(t), 70), 1400) * (np.sin(2 * np.pi * 85 * t) > -0.2) * np.exp(-t * 3.0) * 0.55
    _place(x, rip, 0.08)
    t = _t(0.40)
    _place(x, _lp(_noise(len(t), 71), 2600) * np.sin(np.pi * t / 0.40) * 0.25, 0.60)
    _place(x, _mix(_tick(1500, 0.06), _thunk(210, 0.12, 0.8)), 0.98)
    _place(x, _mix(_thunk(80, 0.28, 1.2), _tick(2600, 0.05)), 1.38)
    t = _t(0.55)
    shimmer = sum(np.sin(2 * np.pi * f * t) for f in (1800, 2400, 3000)) * np.exp(-t * 7) * 0.12
    _place(x, shimmer, 1.40)
    return _norm(x, 0.85)


def armor_hit():
    t = _t(0.25)
    ping = np.sin(2 * np.pi * 2200 * t) * np.exp(-t * 38) * 0.6
    crunch = _hp(_noise(len(t), 72), 2500) * np.exp(-t * 110) * 0.7
    return _norm(ping + crunch + _lp(_noise(len(t), 73), 400) * np.exp(-t * 30) * 0.6, 0.85)


def armor_break():
    t = _t(0.55)
    rng = np.random.default_rng(74)
    crunch = _lp(_noise(len(t), 75), 3500) * np.exp(-t * 9) * (rng.random(len(t)) > 0.35)
    thump = np.sin(2 * np.pi * 90 * t) * np.exp(-t * 14)
    return _norm(_mix(0.8 * crunch + thump, _tick(2000, 0.05)), 0.95)


def body_fall():
    t = _t(0.55)
    thump = np.sin(2 * np.pi * 58 * t) * np.exp(-t * 16) + 0.5 * _lp(_noise(len(t), 90), 300) * np.exp(-t * 22)
    rng = np.random.default_rng(91)
    rattle = _hp(_noise(len(t), 92), 1800) * np.exp(-t * 9) * (rng.random(len(t)) > 0.6) * 0.35
    return _norm(thump + rattle, 0.85)


BUILD = {"shot": gunshot, "reload": reload_full, "reload_tac": reload_tac, "click": click, "hit": hit,
         "kill": kill, "hurt": hurt, "step": step, "enemy_steps": enemy_steps, "whoosh": whoosh,
         "ambience": ambience, "plate_pickup": plate_pickup, "plate_apply": plate_apply,
         "armor_hit": armor_hit, "body_fall": body_fall, "armor_break": armor_break}
POOL = {"shot": 4, "reload": 1, "reload_tac": 1, "click": 2, "hit": 3, "kill": 2, "hurt": 2,
        "step": 3, "whoosh": 1, "ambience": 1, "plate_pickup": 2, "plate_apply": 1, "armor_hit": 3, "body_fall": 2, "armor_break": 1}


def _write(path, x):
    data = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(data.tobytes())


class Sfx:
    def __init__(self, loader, folder: Path):
        folder.mkdir(parents=True, exist_ok=True)
        self.loader, self.paths = loader, {}
        for name, fn in BUILD.items():
            p = folder / f"{name}.wav"
            if not p.exists():
                _write(p, fn())
            self.paths[name] = p
        self.pool = {n: [self._load(n) for _ in range(k)] for n, k in POOL.items()}
        self.idx = {}
        self.free_steps = [self._load("enemy_steps") for _ in range(C.MAX_ENEMIES + 3)]

    def _load(self, name):
        return self.loader.loadSfx(Filename.fromOsSpecific(str(self.paths[name])))

    def play(self, name, vol=1.0, rate=1.0, balance=0.0):
        pool = self.pool.get(name)
        if not pool:
            return
        i = self.idx.get(name, 0)
        self.idx[name] = (i + 1) % len(pool)
        s = pool[i]
        s.setVolume(min(1.0, vol * C.MASTER_VOLUME)); s.setPlayRate(rate); s.setBalance(balance)
        s.play()

    def loop(self, name, vol):
        s = self.pool[name][0]
        s.setLoop(True); s.setVolume(vol * C.MASTER_VOLUME); s.play()
        return s

    def acquire_steps(self):
        if not self.free_steps:
            return None
        s = self.free_steps.pop()
        s.setLoop(True); s.setVolume(0.0); s.play()
        return s

    def release_steps(self, s):
        if s is not None:
            s.stop(); self.free_steps.append(s)
