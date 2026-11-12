"""NeuroStrike — central configuration. Tweak here, not in the engine code."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# --- window / camera -------------------------------------------------------
WIN_W, WIN_H = 1280, 720          # keep 16:9 — detection boxes assume it
HFOV = 90.0                       # horizontal field of view (deg)

# --- vision ---------------------------------------------------------------
YOLO_WEIGHTS = ROOT / "models" / "enemy.pt"
YOLO_CONF = 0.35
DATASET_DIR = ROOT / "dataset"    # F9 auto-labelled dataset output

# --- network --------------------------------------------------------------
WS_HOST, WS_PORT = "0.0.0.0", 8765
STATE_HZ = 30                     # PC -> phone updates per second

# --- player ---------------------------------------------------------------
ARENA_HALF = 36.0
PLAYER_RADIUS = 0.5
AUTO_MOVE = False                 # True = player always moves (press X in-game to toggle)
AUTO_IDLE_SPEED = 0.55            # fraction of BASE_SPEED when joystick is idle
MOUSE_SENS = 0.12                 # deg/pixel (debug mouse look, press M)
FIRE_COOLDOWN = 0.16

# --- enemies --------------------------------------------------------------
MAX_ENEMIES = 5
SPAWN_INTERVAL = 2.5
ENEMY_HP = 3
ENEMY_SPEED = 3.0
ENEMY_HEIGHT = 1.8
ENEMY_HALF_W = 0.5                # bounding half-width incl. arms (used for auto-labels)

# --- radar ----------------------------------------------------------------
CONTACT_TTL = 2.0                 # seconds a detected contact stays on the phone radar

# --- graphics -------------------------------------------------------------
ENEMY_HIGHLIGHT = True            # red hostile outline (what the COLOR fallback sees). If you turn it off,
                                  # re-record the YOLO dataset with the same setting

# --- movement (Warzone-style) -----------------------------------------------
WALK_SPEED = 4.2                  # m/s
SPRINT_SPEED = 6.4                # joystick pushed to the edge (or Shift on PC)
TAC_SPEED = 8.2                   # tactical sprint (TAC button on phone / double-tap Shift)
TAC_TIME = 3.0                    # seconds of tactical sprint
TAC_COOLDOWN = 6.0                # recharge before the next one

# --- weapon ---------------------------------------------------------------
MAG_SIZE = 30
RELOAD_TACTICAL = 1.7             # seconds, rounds left in mag (+1 in the chamber)
RELOAD_EMPTY = 2.3                # seconds, mag empty

# --- audio / performance --------------------------------------------------
SOUND = True
MASTER_VOLUME = 0.8

FULLSCREEN = False                # True = start fullscreen (or press F11 in game)

# --- exhibition -------------------------------------------------------------
VSYNC = False                     # False = no vsync (avoids the 60->30 fps quantisation on slow GPUs)
ATTRACT = True                    # idle screen: AI bot plays by itself until someone picks up the phone
ROUND_TIME = 90                   # seconds per visitor round
RESULTS_TIME = 10                 # seconds the results screen stays up
SHOW_AI_VIEW = True               # picture-in-picture of what YOLO sees (V toggles)

# --- quality presets --------------------------------------------------------
QUALITY = "lite"                  # "lite": no shaders, fake shadows (GPU-less laptops) | "high": real shadows + bloom


def apply_quality(name):
    """Set every graphics knob from one preset. main.py --quality overrides QUALITY."""
    global QUALITY, SHADERS, BLOOM, MSAA, SHADOW_SIZE, FAKE_SHADOWS, CAP_W, CAP_H, VISION_HZ
    QUALITY = name
    if name == "high":
        SHADERS, BLOOM, MSAA, SHADOW_SIZE, FAKE_SHADOWS, CAP_W, CAP_H, VISION_HZ = True, True, 2, 2048, False, 640, 360, 10
    else:
        SHADERS, BLOOM, MSAA, SHADOW_SIZE, FAKE_SHADOWS, CAP_W, CAP_H, VISION_HZ = False, False, 0, 0, True, 480, 270, 8


apply_quality(QUALITY)

# --- hardware radar bridge (ESP32 LED ring etc., see /hardware) -------------
HW_RADAR = False                  # --hw-radar on the command line
HW_RADAR_HOST = "auto"            # "auto" = Wi-Fi broadcast (x.y.z.255), or the ESP32's IP
HW_RADAR_PORT = 4210
HW_RADAR_SERIAL = ""              # e.g. "COM5" to also send over USB (needs pyserial)

# --- armor plates (Warzone style) -------------------------------------------
PLATE_ARMOR = 10                  # armor points one plate adds (armor only, never health)
PLATE_MAX = 30                    # armor cap (3 plates)
PLATE_TIME = 1.8                  # seconds the apply animation takes
PLATES_ON_MAP = 1                 # plates lying around at once
PLATE_SPAWN_INTERVAL = 14.0       # seconds between spawns
PLATE_DROP_CHANCE = 0.0          # chance a killed enemy drops a plate
PLATE_PICKUP_RADIUS = 1.3
