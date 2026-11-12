<div align="center">

```
 ███╗   ██╗███████╗██╗   ██╗██████╗  ██████╗ ███████╗████████╗██████╗ ██╗██╗  ██╗███████╗
 ████╗  ██║██╔════╝██║   ██║██╔══██╗██╔═══██╗██╔════╝╚══██╔══╝██╔══██╗██║██║ ██╔╝██╔════╝
 ██╔██╗ ██║█████╗  ██║   ██║██████╔╝██║   ██║███████╗   ██║   ██████╔╝██║█████╔╝ █████╗
 ██║╚██╗██║██╔══╝  ██║   ██║██╔══██╗██║   ██║╚════██║   ██║   ██╔══██╗██║██╔═██╗ ██╔══╝
 ██║ ╚████║███████╗╚██████╔╝██║  ██║╚██████╔╝███████║   ██║   ██║  ██║██║██║  ██╗███████╗
 ╚═╝  ╚═══╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝╚══════╝
```

**A 3D FPS in Python. Your phone is the controller. YOLO is the sensor. The radar is on your hand.**

`Panda3D` · `YOLO` · `WebSocket` · `Kotlin + Jetpack Compose`

</div>

---

## ⚡ Final configuration

| System | Decision | Implementation |
|---|---|---|
| Player movement | **Joystick only** (auto-run **off**) | Player moves only while the joystick is held. Want auto-run back? `AUTO_MOVE = True` in `config.py`, or press `X` on the PC |
| Aiming | **C — Touch + gyroscope** | Both feed one *relative-delta accumulator*, so they add instead of fighting |
| Radar | **C — Phone radar + PC boxes** | PC draws YOLO boxes on the game view; phone radar plots detected targets |

## 🧠 Architecture

```
            ANDROID PHONE (Kotlin / Compose)
   ┌───────────────────────────────────────────┐
   │ Joystick · Touch aim · Gyro aim · Fire    │
   │ Tactical radar (contacts from YOLO)       │
   └───────────────┬───────────────▲───────────┘
        input @60Hz│               │state @30Hz
                   ▼   WebSocket   │ (pose + contacts + HP)
   ┌───────────────────────────────┴───────────┐
   │  PYTHON — Panda3D game loop               │
   │  movement · aiming · enemy AI · hitscan   │
   └───────┬───────────────────────────▲───────┘
           │ offscreen 640×360 frames  │ detections + track IDs
           ▼  (single-slot mailbox)    │
   ┌───────────────────────────────────┴───────┐
   │  VISION THREAD  (never blocks the game)   │
   │  YOLO / colour fallback → tracker         │
   └───────────────────────┬───────────────────┘
                           ▼
              PC overlay: bounding boxes
```

**Why it won't freeze:** the game hands the newest frame to the vision thread through a one-slot mailbox. If inference is slow, stale frames are *dropped*, never queued.

**Why radar works at all:** a box on screen is converted to a world position (bearing from box centre, depth from box height, pose frozen at capture time). Contacts persist for 2 s in world space, so they stay on the radar after you turn away.

## 🎬 Graphics — two presets

Everything is generated in code — **no asset files**. `python main.py` runs **lite** (built for laptops with no GPU); `--quality high` adds real shadows + bloom if you have a graphics card.

| | Lite (default) | High |
|---|---|---|
| Shadows | **Faked**: each object's real projected shadow + soft contact-AO, baked into one mesh; blob shadow under soldiers | Real-time sun shadow maps |
| Lighting | Fixed-function (cheap) | Per-pixel shaders |
| Bloom / MSAA | off | on |
| Detector frames | 480×270 @ 8 Hz | 640×360 @ 10 Hz |

Both presets share: tileable procedural textures (asphalt + grime, concrete, container ribs, window facades, crates, sandbags, drums), a baked **sky with clouds and sun**, a hazy **distant skyline**, wrecked cars, lamps, sandbag walls and oil drums — the whole map merges into a handful of draw calls.

**Weapon:** carbine with gloved hands drawn in its own depth buffer (never clips into walls). Recoil climbs your aim and partly recovers, bullet spread grows when moving, sway lags behind your look, brass ejects, the bolt cycles, and reload is a full two-handed mag change (empty reloads rack the charging handle). Headshots (instant kill, +150) are real hit zones.

> **Enemy outline vs YOLO:** `ENEMY_HIGHLIGHT` draws the red outline. The colour fallback relies on it. If you later train YOLO and want outline-free enemies, set it to `False` **and re-record the dataset**.

## 🪖 Soldiers & game feel

All assets are generated in code — **no third-party models, so no licence or attribution to worry about.**

- **Soldier:** camo fatigues (procedural multicam texture), plate carrier with pouches, belt, backpack, helmet, goggles, rifle, knee pads, boots. Legs swing while walking; the whole soldier is ~8 draw calls.
- **Hit feedback:** the target flashes white and rocks back when shot, a dust puff + hit marker + tick sound fire, and a headshot pops a banner.
- **Death:** the soldier stops being a target (outline off, footsteps off), falls backwards over half a second with a body-fall thud, lies there, then fades out. Kill streak banners stack on top.
- **World impact:** every shot that lands on the world leaves a dust puff and a **bullet hole** (last 40 kept, fade after 14 s).
- **Damage:** the screen shakes when you're hit (blue flash for armor, red for health).

**Why not downloaded 3D characters?** I tried: the free rigged characters I could fetch were a civilian in a suit and sci-fi blasters, and rigged (skinned) models rendered garbled in my test renderer, so I couldn't verify them. I won't ship what I can't see. If you find a model you like, test it on your laptop first (e.g. drop the `.glb` into Blender or a glTF viewer), and send me a screenshot of it running in-game.

## 🛡 Armor plates (Warzone style)

- Plates lie on the map with a cyan light beam, a ground ring and a slowly spinning steel plate. Two spawn near you at the start of a round, a new one every ~14 s (max 3), and killed enemies drop one 30% of the time. They show as cyan squares on the PC radar.
- **Just walk over one** — it applies itself. Both gloved hands carry the plate up, hold it, and push it down into the vest while the rifle drops away (1.8 s, you can still move but can't shoot or reload). Sounds: pickup chime, velcro rip, plate slide, clack, lock thump, shimmer.
- Each plate = **+10 armor, no health**. Max 3 plates (30). Armor soaks damage first (blue flash + metal ping, crunch when it breaks); only the overflow hurts your HP. At full armor, plates stay on the ground.
- HUD: three plate segments under the HP bar. The phone app doesn't show armor (it ignores the new `armor` field) — no app update needed.
- Tune everything in `config.py` (`PLATE_*`). The attract-mode bot grabs plates too.

## 📡 Hardware radar (optional)

Every enemy and armor plate can also be streamed to a **physical LED-ring radar** built from an ESP32 (about one evening, a few parts).
Run `python main.py --hw-radar`; wiring, parts and firmware are in [`hardware/`](hardware/README.md). Test the PC side without any hardware: `python tools/hw_radar_sim.py`.

## 🎪 Exhibition mode

| Feature | What it does |
|---|---|
| **Attract mode** | Nobody playing? An AI bot patrols, aims, shoots and reloads on its own, with the title screen, your PC's IP and the leaderboard on top. The moment a visitor touches the phone, a round starts |
| **Timed rounds** | 90 s (`ROUND_TIME`), ends early if the player dies. Then a results screen (score, kills, headshots, accuracy, rank) and back to attract after 10 s |
| **Leaderboard** | Top 10 saved to `server/highscores.json` — delete the file to reset before the event |
| **AI Vision panel** | Bottom-left picture-in-picture of the exact frames YOLO receives, with its boxes (`V` toggles). This is the money shot for explaining the project |
| **PC radar** | Top-right tactical radar mirrors the phone's |
| **Streaks & headshots** | Double/triple kill banners, headshot popups |

Tips: use your **phone's hotspot** (venue Wi-Fi often blocks device-to-device traffic), plug the laptop in, set Windows power mode to *Best performance*, and run `python tools/test_client.py` before the doors open. `--no-attract` gives endless free play.

## 🧊 Laptop with no GPU (Snapdragon X etc.)

1. Install the latest GPU driver from Windows Update / your OEM, and the **“OpenCL, OpenGL & Vulkan Compatibility Pack”** from the Microsoft Store — Windows-on-ARM needs it for OpenGL.
2. Check `python -c "import platform; print(platform.machine())"`. `AMD64` = x64 Python running under emulation (works, ~30% slower). Native `ARM64` Python may not have Panda3D wheels yet.
3. Fullscreen on a high-res laptop panel renders MORE pixels and can cost fps; use `--fullscreen --res 1600x900` or stay windowed. Still under 50 fps? `python main.py --res 960x540`, then `--renderer dx9`. The game also shrinks its own window automatically if the first 10 s run slow.
4. Gyro lag is mostly frame rate + Wi-Fi. The phone app now disables Nagle, holds a low-latency Wi-Fi lock, samples the gyro at 200 Hz and sends at 125 Hz; the PC disables Nagle too.

## 🔊 Sound & performance

- **Sound:** all effects (rifle, reload, empty click, hit/kill ticks, damage, footsteps, wind) are synthesised on first run into `server/sounds/`. Enemy footsteps are **directional** — louder when close, panned left/right — so you can hear them coming. Volume: `MASTER_VOLUME` in `config.py`.
- **Reload:** 30-round mag. Tactical reload 1.7 s (keeps a round in the chamber → 31), empty reload 2.3 s. Both tunable in `config.py`.
- **60 fps work (earlier pass):** the YOLO capture camera now renders only when a frame is requested (it used to read the GPU back *every* frame — the biggest stall), static map geometry is merged into a few draw calls, HUD text updates 10×/s, YOLO leaves CPU cores free, and **auto-quality** drops shadows, then bloom, if the first seconds run under ~52 fps. 
- Watch the `fps` counter top-right. The game is capped by your monitor's refresh (vsync), so 60 Hz = 60 fps max.

## 🚀 Quick start

### 1 · PC server
```bash
cd server
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py                                         # or ./run.sh · run.bat
```
The console prints `Phone → enter 192.168.x.x`. **Allow Python through your firewall** (private networks) or the phone can't connect.

No phone yet? Drive it from the keyboard (`WASD`, `M` for mouse-look, click to fire) and test the network with:
```bash
python tools/test_client.py 127.0.0.1 10      # fake phone: input rate, state rate, RTT
```

### 2 · Android app
1. Open the `android/` folder in **Android Studio** (Koala+). Let Gradle sync.
2. Run on a phone (Android 8+, USB debugging on).
3. Enter the PC's IP → **CONNECT**. Same Wi-Fi as the PC (5 GHz strongly recommended).

## 🎮 Controls

| Phone | Does |
|---|---|
| Left joystick | Sets movement direction (relative to where you look) |
| Right half drag | Touch aim |
| Tilt / rotate phone | Gyro aim (toggle `GYRO`, `INV-Y`, sliders under ⚙) |
| FIRE | Hold to shoot — phone buzzes when you take damage |
| **R** button | Reload (also auto-reloads when the mag is empty) |
| Stick pushed to the edge | **Sprint** (can't shoot while sprinting, like Warzone) |
| **TAC** button | **Tactical sprint** — 3 s burst, ring shows recharge (6 s) |

| PC (debug) | Does |
|---|---|
| `W A S D` · `Mouse1` · `M` | Move · fire · toggle mouse-look |
| `Shift` (hold) / double-tap `Shift` | Sprint / tactical sprint |
| `R` | Reload |
| `X` | Toggle auto-run (off by default) |
| `B` | Toggle detection boxes |
| `F9` | Record auto-labelled YOLO dataset |
| `F11` | Fullscreen on/off (borderless; also `python main.py --fullscreen`) |
| `Esc` | Quit |

## 👁 YOLO — read this

A stock YOLO model **does not know what a NeuroStrike enemy is**. Out of the box the server uses a *colour-segmentation fallback* (HUD says `COLOR`) so the whole pipeline works on day one. To get real YOLO:

1. Play with `F9` recording on for ~5–10 min. The game writes frames **and perfect labels** (it projects each enemy's 3D box to screen, skips occluded ones, keeps ~10 % negatives) → `server/dataset/`.
2. `pip install -r requirements-yolo.txt` then `python tools/train.py --epochs 60`
3. Restart `main.py`. It finds `models/enemy.pt` and the HUD switches to `YOLO`.

Aim for **800+ images**. Fewer will overfit to the arena.

## 🔌 Protocol (JSON over WebSocket, port 8765)

| Dir | Message |
|---|---|
| phone → PC | `{"t":"input","jx","jy","dyaw","dpitch","fire"}` — `jx/jy` joystick −1..1, `dyaw/dpitch` degrees accumulated since the last send |
| phone → PC | `{"t":"ping","ts"}` → PC replies `{"t":"pong","ts"}` (RTT shown on the phone) |
| PC → phone | `{"t":"state","px","py","h","hp","score","hurt","alive","src","ms","contacts":[{"id","x","y","c","a"}]}` |

## 🗂 Layout

```
NeuroStrike/
├─ server/
│  ├─ main.py        entry point            ├─ vision.py   detector thread + tracker
│  ├─ game.py        Panda3D game loop      ├─ net.py      WebSocket server (own thread)
│  ├─ world.py       arena, collision, rays ├─ config.py   every tunable in one place
│  └─ tools/         train.py · test_client.py
├─ hardware/         ESP32 LED-ring radar (firmware + build guide)
└─ android/          Kotlin + Compose app (Ui · NetClient · GyroAim · InputController)
```

## 🛠 Troubleshooting

| Symptom | Fix |
|---|---|
| Gradle: *plugin 'com.android.application' was not found* | Open the **`android`** folder itself in Android Studio (the one containing `settings.gradle.kts`), not the parent. Don't edit the Gradle files; plugin versions live in `settings.gradle.kts`. Use JDK 17 (Android Studio's bundled one is fine) |
| Phone stuck on CONNECTING | Same Wi-Fi? Firewall? Guest/AP-isolation networks block device-to-device traffic |
| Gyro turns the wrong way | Flip the sign on the marked lines in `GyroAim.kt` (or use `INV-Y` for pitch) |
| Boxes misaligned | Don't resize the window; detection assumes 16:9 (`config.py`) |
| Radar markers drift | Depth comes from box height (assumes 2 m enemies). Partly-clipped boxes read too far |
| Low FPS | Lower `CAP_W/CAP_H` or `VISION_HZ` in `config.py` |

## ✅ Status

Verified in a sandbox (headless software renderer): all Python compiles; geometry/collision/ray helpers; colour detector + tracker (stable IDs); vision worker; live WebSocket round trip (input → state, ping/pong).
Also ran the full game loop headless (software renderer, 90 frames): world, enemies, capture camera, detector thread, contacts, shooting.
Also ran attract → round → results → attract end to end, the bot, headshots, reload, sprint, high scores; game-logic CPU cost was ~0.6 ms/frame.
**Not verified:** real GPU frame rate on your laptop, how the weapon is *shaded* (the sandbox renderer can't shade flat-coloured parts), audio output, high-quality shadows/bloom, and the Android app (no SDK) — expect small first-run fixes.
