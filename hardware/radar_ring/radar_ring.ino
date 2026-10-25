/*
 * NeuroStrike hardware radar  -  ESP32 + WS2812B (NeoPixel) LED ring
 * ------------------------------------------------------------------
 * The game streams every enemy / armor plate as (bearing, distance). This sketch lights the LED
 * that points at it, colours it by distance and makes it flare when the radar sweep passes over it.
 *
 *   top LED (straight ahead)  : white marker, cyan while the player has armor, blinks red at low health
 *   red / orange / yellow     : enemy near (<10 m) / mid (<20 m) / far
 *   blue                      : armor plate
 *   cyan trail                : the rotating radar sweep (one turn every 2.6 s, like the phone radar)
 *
 * Input: UDP port 4210 over Wi-Fi (default)  and/or USB serial 115200 (one packet per line).
 * Packet: NS1,<mode>,<hp>,<armor>|<bearing>,<dist>,<type>;...     (see server/hwradar.py)
 *
 * Libraries (Arduino IDE -> Library Manager): "Adafruit NeoPixel".   Board: "ESP32 Dev Module".
 */
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <Adafruit_NeoPixel.h>

// ===================== EDIT THESE =====================
const char* WIFI_SSID = "YourHotspot";     // the SAME network the PC runs on (phone hotspot is ideal)
const char* WIFI_PASS = "YourPassword";
#define LED_PIN          5                 // ESP32 GPIO connected to the ring's DIN (through ~330 ohm)
#define NUM_LEDS         60                // 12 / 16 / 24 / 35 / 60 ... whatever ring you bought
#define CLOCKWISE        true              // set false if blips move the wrong way round the ring
#define LED_ZERO_OFFSET  0                 // LED index that sits at the TOP of your build (straight ahead)
#define BRIGHTNESS       90                // 0-255 (power: 60 LEDs at full white can pull ~3.6 A!)
const uint16_t UDP_PORT = 4210;
// ======================================================

struct Blip { float bearing; float dist; char type; };
static Blip     blips[16];
static int      nBlips = 0;
static char     gMode = 'a';
static int      gHp = 100, gArmor = 0;
static uint32_t lastRx = 0;
static uint8_t  fb[NUM_LEDS][3];           // frame buffer, so overlapping blips can add up safely

static Adafruit_NeoPixel strip(NUM_LEDS, LED_PIN, NEO_GRB + NEO_KHZ800);
static WiFiUDP udp;
static char serialBuf[320];
static int  serialLen = 0;

static bool parsePacket(char* s) {
  if (strncmp(s, "NS1,", 4) != 0) return false;
  char* bar = strchr(s, '|');
  if (!bar) return false;
  *bar = 0;
  char m; int h, a;
  if (sscanf(s + 4, "%c,%d,%d", &m, &h, &a) != 3) return false;
  gMode = m; gHp = h; gArmor = a;
  nBlips = 0;
  char* save = nullptr;
  for (char* tok = strtok_r(bar + 1, ";", &save); tok && nBlips < 16; tok = strtok_r(nullptr, ";", &save)) {
    float b, d; char t;
    if (sscanf(tok, "%f,%f,%c", &b, &d, &t) == 3) {
      blips[nBlips].bearing = b; blips[nBlips].dist = d; blips[nBlips].type = t;
      nBlips++;
    }
  }
  lastRx = millis();
  return true;
}

static int ledFor(float bearing) {           // bearing (deg clockwise from ahead) -> LED index
  while (bearing < 0) bearing += 360.0f;
  int i = (int)roundf(bearing / 360.0f * NUM_LEDS) % NUM_LEDS;
  if (!CLOCKWISE) i = (NUM_LEDS - i) % NUM_LEDS;
  return (i + LED_ZERO_OFFSET) % NUM_LEDS;
}

static void addPx(int i, float r, float g, float b) {
  int R = fb[i][0] + (int)r, G = fb[i][1] + (int)g, B = fb[i][2] + (int)b;
  fb[i][0] = R > 255 ? 255 : R; fb[i][1] = G > 255 ? 255 : G; fb[i][2] = B > 255 ? 255 : B;
}

static void show() {
  for (int i = 0; i < NUM_LEDS; i++) strip.setPixelColor(i, fb[i][0], fb[i][1], fb[i][2]);
  strip.show();
}

static void render() {
  memset(fb, 0, sizeof(fb));
  uint32_t now = millis();
  bool live = (now - lastRx) < 1500;
  float sweep = fmodf(now / 2600.0f, 1.0f) * 360.0f;          // current sweep bearing

  for (int k = 0; k < 10; k++) {                              // sweep head + fading trail
    float f = (10 - k) / 10.0f; f = f * f * (live ? 0.40f : 0.18f);
    addPx(ledFor(sweep - k * 360.0f / NUM_LEDS), 0, 190 * f, 170 * f);
  }

  if (live) {
    for (int i = 0; i < nBlips; i++) {
      const Blip& b = blips[i];
      int led = ledFor(b.bearing);
      if (b.type == 'P') {                                    // armor plate: steady blue
        addPx(led, 0, 110, 255);
        continue;
      }
      float since = fmodf(sweep - b.bearing + 720.0f, 360.0f); // degrees since the sweep passed it
      float flare = 0.25f + 0.75f * powf(1.0f - since / 360.0f, 2.0f);
      float r, g, bl = 0;
      if (b.dist < 10.0f)      { r = 255; g = 15;  }          // near: red
      else if (b.dist < 20.0f) { r = 255; g = 110; }          // mid: orange
      else                     { r = 200; g = 190; }          // far: yellow
      addPx(led, r * flare, g * flare, bl);
    }
  }

  bool lowHp = gHp < 30 && ((now / 250) % 2 == 0) && gMode == 'p';   // forward marker
  if (lowHp)           addPx(ledFor(0), 255, 0, 0);
  else if (gArmor > 0) addPx(ledFor(0), 0, 120, 160);
  else                 addPx(ledFor(0), 70, 70, 70);
  show();
}

static void bootAnimation(uint32_t ms) {                       // shown while Wi-Fi connects
  uint32_t t0 = millis();
  while (millis() - t0 < ms && WiFi.status() != WL_CONNECTED) {
    memset(fb, 0, sizeof(fb));
    int head = (millis() / 40) % NUM_LEDS;
    for (int k = 0; k < 8; k++) addPx((head - k + NUM_LEDS) % NUM_LEDS, 0, 40 * (8 - k) / 8.0f, 90 * (8 - k) / 8.0f);
    show();
    delay(20);
  }
}

void setup() {
  Serial.begin(115200);
  strip.begin();
  strip.setBrightness(BRIGHTNESS);
  strip.show();
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  bootAnimation(15000);
  if (WiFi.status() == WL_CONNECTED) {
    udp.begin(UDP_PORT);
    Serial.print("NeuroStrike radar online. ESP32 IP: ");
    Serial.println(WiFi.localIP());                           // use with:  python main.py --hw-radar <this IP>
  } else {
    Serial.println("Wi-Fi not connected - USB serial input still works.");
  }
}

void loop() {
  int n = udp.parsePacket();
  if (n > 0) {
    static char buf[320];
    int len = udp.read(buf, sizeof(buf) - 1);
    if (len > 0) { buf[len] = 0; parsePacket(buf); }
  }
  while (Serial.available()) {                                // USB serial input (optional)
    char c = (char)Serial.read();
    if (c == '\n') { serialBuf[serialLen] = 0; parsePacket(serialBuf); serialLen = 0; }
    else if (serialLen < (int)sizeof(serialBuf) - 1) serialBuf[serialLen++] = c;
  }
  static uint32_t lastDraw = 0;
  if (millis() - lastDraw >= 16) { lastDraw = millis(); render(); }

  static uint32_t lastTry = 0;                                // keep trying to rejoin Wi-Fi
  if (WiFi.status() != WL_CONNECTED && millis() - lastTry > 8000) {
    lastTry = millis();
    WiFi.reconnect();
  }
}
