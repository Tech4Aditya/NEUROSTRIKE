"""NeuroStrike server entry point.

    python main.py                      # lite mode (no GPU needed), 1280x720
    python main.py --quality high       # real shadows + bloom (needs a GPU)
    python main.py --res 960x540        # smaller window = faster
    python main.py --fullscreen --res 1600x900   # fullscreen (F11 toggles in game)
    python main.py --renderer dx9       # try DirectX instead of OpenGL (helps on some Windows-on-ARM drivers)
"""
import argparse

import config as C


def main():
    ap = argparse.ArgumentParser(description="NeuroStrike - phone-controlled FPS with YOLO detection")
    ap.add_argument("--detector", choices=["auto", "yolo", "color"], default="auto",
                    help="auto = YOLO if models/enemy.pt exists, else colour fallback")
    ap.add_argument("--quality", choices=["lite", "high"], default=C.QUALITY)
    ap.add_argument("--res", default=None, help="window size, 16:9, e.g. 960x540")
    ap.add_argument("--renderer", choices=["auto", "gl", "dx9", "software"], default="auto")
    ap.add_argument("--fullscreen", action="store_true", help="start fullscreen (F11 toggles in game)")
    ap.add_argument("--no-attract", action="store_true", help="skip the idle demo screen (free play, no timer)")
    a = ap.parse_args()

    C.apply_quality(a.quality)
    if a.res:
        C.WIN_W, C.WIN_H = (int(v) for v in a.res.lower().split("x"))
    if a.fullscreen:
        C.FULLSCREEN = True
        if not a.res:
            C.WIN_W, C.WIN_H = 1920, 1080          # real fullscreen mode; override with --res
    if a.no_attract:
        C.ATTRACT = False

    from panda3d.core import loadPrcFileData
    pipe = {"gl": "pandagl", "dx9": "pandadx9", "software": "p3tinydisplay"}.get(a.renderer)
    if pipe:
        loadPrcFileData("", f"load-display {pipe}")

    from game import NeuroStrike          # imported late so the settings above are in place
    NeuroStrike(a.detector).run()


if __name__ == "__main__":
    main()
