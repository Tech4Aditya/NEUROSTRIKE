"""Split the auto-labelled dataset (press F9 in-game) and train YOLO.
    python tools/train.py [--epochs 60]
Result is copied to models/enemy.pt, which main.py picks up automatically."""
import argparse
import random
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--base", default="yolov8n.pt")
    args = ap.parse_args()

    src = ROOT / "dataset"
    imgs = sorted((src / "images").glob("*.jpg"))
    if len(imgs) < 200:
        print(f"Only {len(imgs)} images. Record at least ~800 (F9 in-game, ~5 min of play).")
    random.seed(0); random.shuffle(imgs)
    cut = int(len(imgs) * 0.85)
    out = ROOT / "dataset_split"
    shutil.rmtree(out, ignore_errors=True)
    for split, group in (("train", imgs[:cut]), ("val", imgs[cut:])):
        (out / "images" / split).mkdir(parents=True); (out / "labels" / split).mkdir(parents=True)
        for im in group:
            shutil.copy(im, out / "images" / split / im.name)
            shutil.copy(src / "labels" / f"{im.stem}.txt", out / "labels" / split / f"{im.stem}.txt")
    (out / "data.yaml").write_text(f"path: {out.as_posix()}\ntrain: images/train\nval: images/val\n"
                                   "names:\n  0: enemy\n")

    from ultralytics import YOLO
    model = YOLO(args.base)
    model.train(data=str(out / "data.yaml"), epochs=args.epochs, imgsz=640, project=str(ROOT / "runs"),
                name="neurostrike", exist_ok=True)
    best = ROOT / "runs" / "neurostrike" / "weights" / "best.pt"
    (ROOT / "models").mkdir(exist_ok=True)
    shutil.copy(best, ROOT / "models" / "enemy.pt")
    print("Saved models/enemy.pt — restart main.py")


if __name__ == "__main__":
    main()
