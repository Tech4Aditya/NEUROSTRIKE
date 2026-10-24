"""Procedural textures (no asset files). Tileable fractal noise via FFT."""
import cv2
import numpy as np
from panda3d.core import SamplerState, Texture

_cache = {}


def _fractal(n, beta, seed):
    rng = np.random.default_rng(seed)
    fx = np.fft.fftfreq(n)
    f2 = fx[:, None] ** 2 + fx[None, :] ** 2
    f2[0, 0] = 1.0
    spec = (rng.standard_normal((n, n)) + 1j * rng.standard_normal((n, n))) / f2 ** (beta / 2)
    spec[0, 0] = 0
    img = np.fft.ifft2(spec).real
    img -= img.min()
    return img / img.max()


def _tex(name, rgb, flip=True):
    arr = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    arr = np.ascontiguousarray(arr[::-1] if flip else arr)
    h, w, _ = arr.shape
    t = Texture(name)
    t.setup2dTexture(w, h, Texture.TUnsignedByte, Texture.FRgb)
    t.setRamImageAs(arr.tobytes(), "RGB")
    t.setMinfilter(SamplerState.FT_linear_mipmap_linear)
    t.setMagfilter(SamplerState.FT_linear)
    t.setAnisotropicDegree(8)
    t.setWrapU(SamplerState.WM_repeat)
    t.setWrapV(SamplerState.WM_repeat)
    return t


def concrete():
    if "concrete" not in _cache:
        n = 512
        lum = 0.46 + 0.30 * (_fractal(n, 2.6, 1) - 0.5) + 0.12 * (_fractal(n, 1.0, 2) - 0.5)
        for k in range(0, n, 128):                       # panel seams
            lum[k:k + 2, :] *= 0.68
            lum[:, k:k + 2] *= 0.68
        _cache["concrete"] = _tex("concrete", lum[..., None] * np.array([1.0, 0.98, 0.94]))
    return _cache["concrete"]


def asphalt():
    if "asphalt" not in _cache:
        n = 512
        rng = np.random.default_rng(5)
        lum = 0.17 + 0.10 * (_fractal(n, 2.4, 3) - 0.5) + 0.08 * (_fractal(n, 0.8, 4) - 0.5)
        lum += (rng.random((n, n)) > 0.994) * 0.25      # bright aggregate speckle
        _cache["asphalt"] = _tex("asphalt", lum[..., None] * np.array([1.0, 1.0, 1.04]))
    return _cache["asphalt"]


def container(i):
    colors = [(0.28, 0.34, 0.20), (0.22, 0.30, 0.38), (0.55, 0.48, 0.34), (0.15, 0.38, 0.38)]
    key = f"container{i % 4}"
    if key not in _cache:
        n = 512
        x = np.arange(n)[None, :] / n
        ribs = 0.80 + 0.20 * np.sin(x * 2 * np.pi * 24)
        dirt = _fractal(n, 2.2, 10 + i)
        lum = ribs * (0.85 + 0.30 * (dirt - 0.5))
        lum = np.repeat(lum, n, axis=0) if lum.shape[0] == 1 else lum
        lum = np.broadcast_to(lum, (n, n)).copy()
        lum[:24, :] *= 0.55; lum[-24:, :] *= 0.55        # top/bottom rails
        lum[:, :12] *= 0.6; lum[:, -12:] *= 0.6          # corner posts
        _cache[key] = _tex(key, lum[..., None] * np.array(colors[i % 4]) * 1.5)
    return _cache[key]


def facade():
    if "facade" not in _cache:
        n = 512
        rng = np.random.default_rng(7)
        lum = 0.50 + 0.25 * (_fractal(n, 2.6, 20) - 0.5) + 0.08 * (_fractal(n, 1.0, 21) - 0.5)
        img = lum[..., None] * np.array([1.0, 0.97, 0.92])
        cols, rows = 4, 3
        cw, ch = n // cols, n // rows
        for r in range(rows):
            for c in range(cols):
                x0, y0 = c * cw + 24, r * ch + 30
                x1, y1 = x0 + cw - 48, y0 + ch - 70
                img[y0 - 4:y1 + 4, x0 - 4:x1 + 4] = (0.72, 0.72, 0.70)        # frame
                grad = np.linspace(0.10, 0.32, y1 - y0)[:, None, None]
                glass = grad * np.array([0.7, 0.95, 1.2])
                if rng.random() < 0.15:
                    glass = np.broadcast_to(np.array([0.75, 0.62, 0.35]) * (0.8 + 0.2 * grad), glass.shape)
                img[y0:y1, x0:x1] = glass
        _cache["facade"] = _tex("facade", img)
    return _cache["facade"]


def crate():
    if "crate" not in _cache:
        n = 256
        grain = cv2.GaussianBlur(_fractal(n, 2.0, 30), (41, 1), 0)
        grain = (grain - grain.min()) / (grain.max() - grain.min())
        lum = 0.75 + 0.45 * (grain - 0.5)
        for k in range(0, n, 64):
            lum[k:k + 2, :] *= 0.45                      # plank seams
        lum[:16, :] *= 0.7; lum[-16:, :] *= 0.7; lum[:, :16] *= 0.7; lum[:, -16:] *= 0.7
        _cache["crate"] = _tex("crate", lum[..., None] * np.array([0.52, 0.34, 0.18]))
    return _cache["crate"]


def _tex_rgba(name, rgba, clamp=False):
    arr = np.ascontiguousarray((np.clip(rgba, 0, 1) * 255).astype(np.uint8)[::-1])
    h, w, _ = arr.shape
    t = Texture(name)
    t.setup2dTexture(w, h, Texture.TUnsignedByte, Texture.FRgba)
    t.setRamImageAs(arr.tobytes(), "RGBA")
    t.setMinfilter(SamplerState.FT_linear_mipmap_linear)
    t.setMagfilter(SamplerState.FT_linear)
    mode = SamplerState.WM_clamp if clamp else SamplerState.WM_repeat
    t.setWrapU(mode); t.setWrapV(mode)
    return t


def sky(haze, zenith, sun_dir):
    """Equirectangular sky: gradient + sun glow/disc + fractal clouds (baked once, free at runtime)."""
    if "sky" not in _cache:
        W, H = 1024, 512
        az = (np.arange(W) + 0.5) / W * 2 * np.pi
        el = np.radians(-12 + (np.arange(H) + 0.5) / H * 102.0)
        AZ, EL = np.meshgrid(az, el)
        dx, dy, dz = np.cos(EL) * np.cos(AZ), np.cos(EL) * np.sin(AZ), np.sin(EL)
        s = np.array(sun_dir, float) / np.linalg.norm(sun_dir)
        dot = dx * s[0] + dy * s[1] + dz * s[2]
        t = np.clip(dz, 0, 1) ** 0.55
        haze, zenith = np.array(haze), np.array(zenith)
        col = haze + (zenith - haze) * t[..., None]
        col = col + (np.exp((dot - 1) * 14) * 0.55)[..., None] * np.array([1.0, 0.92, 0.75])
        col = col + np.clip((dot - 0.9995) / 0.0004, 0, 1)[..., None]
        f = _fractal(1024, 2.7, 40)[:H, :]
        cov = np.clip((f - 0.50) / 0.20, 0, 1) * np.clip(dz * 3.2, 0, 1) * 0.92
        shade = 0.80 + 0.20 * np.clip(dot + 0.3, 0, 1)
        col = col * (1 - cov[..., None]) + shade[..., None] * cov[..., None]
        t_ = _tex("sky", col, flip=False)               # row 0 = lowest elevation = v 0
        t_.setWrapV(SamplerState.WM_clamp)
        _cache["sky"] = t_
    return _cache["sky"]


def grime():
    """Transparent dirt/oil overlay that breaks up the repeating asphalt."""
    if "grime" not in _cache:
        n = 512
        a = np.clip((_fractal(n, 2.2, 50) - 0.55) / 0.30, 0, 1) * 0.5
        a += np.clip((_fractal(n, 1.6, 51) - 0.70) / 0.12, 0, 1) * 0.35
        rgba = np.zeros((n, n, 4)); rgba[..., :3] = (0.05, 0.045, 0.04); rgba[..., 3] = np.clip(a, 0, 0.7)
        _cache["grime"] = _tex_rgba("grime", rgba)
    return _cache["grime"]


def blob():
    if "blob" not in _cache:
        n = 64
        y, x = np.mgrid[-1:1:n * 1j, -1:1:n * 1j]
        r = np.clip(1 - np.hypot(x, y), 0, 1)
        rgba = np.zeros((n, n, 4)); rgba[..., 3] = (r ** 1.4) * 0.6
        _cache["blob"] = _tex_rgba("blob", rgba, clamp=True)
    return _cache["blob"]


def muzzle():
    if "muzzle" not in _cache:
        n = 128
        y, x = np.mgrid[-1:1:n * 1j, -1:1:n * 1j]
        r, th = np.hypot(x, y), np.arctan2(y, x)
        spikes = np.abs(np.cos(4 * th)) ** 10 * np.exp(-r * 2.4)
        core = np.exp(-r ** 2 * 14)
        a = np.clip(spikes * 1.3 + core, 0, 1) * np.clip(1.2 - r, 0, 1)
        rgba = np.zeros((n, n, 4))
        rgba[..., 0], rgba[..., 1], rgba[..., 2] = 1.0, 0.80 + 0.2 * core, 0.35 + 0.6 * core
        rgba[..., 3] = a
        _cache["muzzle"] = _tex_rgba("muzzle", rgba, clamp=True)
    return _cache["muzzle"]


def sandbag():
    if "sandbag" not in _cache:
        n = 256
        yy, xx = np.mgrid[0:n, 0:n]
        row, ry = yy // 64, yy % 64
        xs = (xx + (row % 2) * 64) % 128
        shade = (0.72 + 0.28 * np.sin(np.pi * ry / 64)) * (0.8 + 0.2 * np.sin(np.pi * xs / 128))
        lum = shade * (0.82 + 0.36 * (_fractal(n, 1.8, 60) - 0.5))
        _cache["sandbag"] = _tex("sandbag", lum[..., None] * np.array([0.58, 0.52, 0.37]))
    return _cache["sandbag"]


def drum():
    """Grey ribbed steel; tint per instance with setColor."""
    if "drum" not in _cache:
        n = 256
        ribs = 0.72 + 0.28 * np.cos(np.arange(n)[:, None] / n * 2 * np.pi * 6) ** 2
        lum = ribs * (0.85 + 0.30 * (_fractal(n, 2.2, 61) - 0.5))
        _cache["drum"] = _tex("drum", np.repeat(lum[..., None], 3, axis=2))
    return _cache["drum"]
