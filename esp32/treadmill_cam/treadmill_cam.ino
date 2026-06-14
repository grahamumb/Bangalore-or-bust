// Bangalore-or-bust — ESP32-CAM firmware
//
// Photographs the treadmill console on request and streams the photos to the
// Raspberry Pi over UART.
//
// Protocol:
//   Pi  -> ESP32 : "CAPTURE\n"
//   ESP32 -> Pi  : for each of 4 frames:
//                      "IMG <index> <byte_length>\n"
//                      <byte_length> raw JPEG bytes
//                  "DONE\n"
//
// Board: "AI Thinker ESP32-CAM" in the Arduino IDE.
// The console cycles through its metrics, so we space the 4 frames 5s apart to
// catch the full cycle (time / distance / calories / speed).
//
// NOTE: UART is a short, wired link. If the Pi can't be cabled to the
// treadmill, switching this sketch to Wi-Fi (POST the JPEGs over HTTP) is the
// natural alternative — but the Pi side here speaks UART, per the design.

#include "esp_camera.h"

#define BAUD 115200
#define FRAME_COUNT 4
#define FRAME_INTERVAL_MS 5000

// --- AI Thinker ESP32-CAM pin map ---
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

void initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  // VGA keeps each JPEG ~30KB so UART transfer stays manageable.
  config.frame_size = FRAMESIZE_VGA;
  config.jpeg_quality = 12;
  config.fb_count = 1;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    // Can't recover; loop forever so the watchdog/USB log shows the failure.
    while (true) { delay(1000); }
  }
}

void sendFrame(int index) {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    Serial.printf("IMG %d 0\n", index);
    return;
  }
  Serial.printf("IMG %d %u\n", index, fb->len);
  Serial.write(fb->buf, fb->len);
  esp_camera_fb_return(fb);
}

void setup() {
  Serial.begin(BAUD);
  initCamera();
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd == "CAPTURE") {
      for (int i = 0; i < FRAME_COUNT; i++) {
        sendFrame(i);
        if (i < FRAME_COUNT - 1) delay(FRAME_INTERVAL_MS);
      }
      Serial.print("DONE\n");
    }
  }
}
