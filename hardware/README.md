# 📡 NeuroStrike hardware radar

A physical radar for the exhibition: a ring of LEDs where every enemy in the game appears at its real bearing,
coloured by distance, with a rotating sweep. Armor plates show up blue.

```
 PC (game)  --UDP broadcast / USB serial-->  ESP32  -->  WS2812B LED ring
```

The game already knows every target as *(bearing, distance)* — the same list the phone radar draws. `server/hwradar.py`
streams it at 20 Hz; the ESP32 just draws it. Nothing in the game logic changes.

## Parts (cheap, one evening)
| Part | Notes |
|---|---|
| ESP32 DevKit (any) | the brain; has Wi-Fi |
| WS2812B / NeoPixel **ring** | 60 LEDs = 6° resolution (24 works, 12 is too coarse) |
| 5 V power supply | 2 A+ for a 60-ring at the default brightness (full white would be ~3.6 A) |
| 330 Ω resistor, 1000 µF capacitor | data-line resistor; capacitor across the ring's 5 V/GND |
| Optional | 74AHCT125 level shifter if the ring flickers; acrylic disc + diffuser paper on top |

## Wiring
| ESP32 | Ring |
|---|---|
| GPIO 5 → 330 Ω → | DIN |
| GND (common!) | GND (and the PSU's GND) |
| USB power | — |
| — | 5 V from the PSU (not from the ESP32 pin) |

## Flash it
1. Arduino IDE → Boards Manager → install **esp32**; Library Manager → install **Adafruit NeoPixel**.
2. Open `radar_ring/radar_ring.ino`, edit `WIFI_SSID`, `WIFI_PASS`, `NUM_LEDS`, `LED_PIN` at the top. Board: *ESP32 Dev Module*. Upload.
3. Open the Serial Monitor (115200): it prints `ESP32 IP: 192.168.x.y`.

## Run
Put the **PC and the ESP32 on the same network** (your phone's hotspot is ideal — same one the game phone uses).
```bash
python main.py --hw-radar                 # broadcast to the whole Wi-Fi (no IP needed)
python main.py --hw-radar 192.168.43.77   # or send straight to the ESP32's IP
python main.py --hw-serial COM5           # or USB cable (pip install pyserial)
```
No hardware yet? `python tools/hw_radar_sim.py` shows the same data as an ASCII radar, to test the PC side.

## What you see
- **Top LED** = straight ahead. White normally, cyan when the player has armor, flashing red at low health.
- **Red / orange / yellow** = enemy within 10 m / 20 m / further. It flares when the sweep passes it, then fades — like a real radar.
- **Blue** = armor plate. **Cyan trail** = the sweep. Dim sweep only = no signal / nobody playing.

## Troubleshooting
| Symptom | Fix |
|---|---|
| Nothing lights except the sweep | No packets: same network? firewall (allow Python on private networks)? try `--hw-radar <ESP32 IP>` instead of broadcast |
| Blips go the wrong way round | `#define CLOCKWISE false` |
| Blips are rotated | change `LED_ZERO_OFFSET` until the white marker sits at the top of your build |
| Random flicker / wrong colours | add the 330 Ω + capacitor, shorten the data wire, or use a level shifter |
| Phone hotspot blocks it | some hotspots isolate clients; use a travel router (cheap, and ideal for exhibitions) |

## Upgrades (say the word and I'll write the firmware)
- **Round 240×240 TFT (GC9A01)** — a proper green radar screen with sweep line, range rings and labelled blips.
- **Servo/stepper sweep arm** with an LED or laser pointer that physically points at the nearest enemy.
- **Concentric rings** (e.g. 12 + 24 + 36 LEDs) so distance is a ring, not just a colour.
