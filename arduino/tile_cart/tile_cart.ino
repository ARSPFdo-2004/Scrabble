/*
 * tile_cart.ino
 *
 * ESP32 firmware for the motorised tile cart.
 *
 * Hardware:
 *   - ESP32 development board
 *   - L298N (or similar) dual H-bridge motor driver
 *     · IN1 = GPIO 25, IN2 = GPIO 26 (Motor A – left wheel)
 *     · IN3 = GPIO 27, IN4 = GPIO 14 (Motor B – right wheel)
 *     · ENA = GPIO 32 (PWM), ENB = GPIO 33 (PWM)
 *   - Two IR proximity sensors (end-stop detection)
 *     · SENSOR_HUMAN = GPIO 34 (human side)
 *     · SENSOR_AI    = GPIO 35 (AI / plotter side)
 *   - Status RGB LED (optional): R=GPIO 2, G=GPIO 4, B=GPIO 5
 *
 * Communication:
 *   - Serial2 (GPIO 16 RX / GPIO 17 TX) at 9600 baud to Raspberry Pi
 *   - Messages are newline-delimited JSON (same protocol as Arduino)
 *
 * Incoming JSON:
 *   {"type":"move","player":"human"|"ai"}
 *   {"type":"stop"}
 *   {"type":"home"}
 *
 * Outgoing JSON:
 *   {"type":"arrived","player":"human"|"ai"}
 *   {"type":"status","state":"idle"|"moving"|"arrived"}
 */

#include <ArduinoJson.h>

// ── Pin definitions ───────────────────────────────────────────────────────
#define MOTOR_A_IN1  25
#define MOTOR_A_IN2  26
#define MOTOR_B_IN3  27
#define MOTOR_B_IN4  14
#define MOTOR_A_ENA  32   // PWM channel 0
#define MOTOR_B_ENB  33   // PWM channel 1

#define SENSOR_HUMAN 34   // IR sensor, active LOW
#define SENSOR_AI    35

#define LED_R 2
#define LED_G 4
#define LED_B 5

// ── PWM config ─────────────────────────────────────────────────────────────
#define PWM_FREQ   5000
#define PWM_RES    8       // 8-bit (0-255)
#define MOTOR_SPEED 180    // default drive speed (0-255)

// ── State ──────────────────────────────────────────────────────────────────
enum CartState { IDLE, MOVING_TO_HUMAN, MOVING_TO_AI };
CartState cartState = IDLE;
char targetPlayer[8] = "";

// ── Motor helpers ──────────────────────────────────────────────────────────

void motorSetup() {
  pinMode(MOTOR_A_IN1, OUTPUT);
  pinMode(MOTOR_A_IN2, OUTPUT);
  pinMode(MOTOR_B_IN3, OUTPUT);
  pinMode(MOTOR_B_IN4, OUTPUT);

  ledcSetup(0, PWM_FREQ, PWM_RES);
  ledcSetup(1, PWM_FREQ, PWM_RES);
  ledcAttachPin(MOTOR_A_ENA, 0);
  ledcAttachPin(MOTOR_B_ENB, 1);
}

void driveForward(int speed = MOTOR_SPEED) {
  digitalWrite(MOTOR_A_IN1, HIGH); digitalWrite(MOTOR_A_IN2, LOW);
  digitalWrite(MOTOR_B_IN3, HIGH); digitalWrite(MOTOR_B_IN4, LOW);
  ledcWrite(0, speed);
  ledcWrite(1, speed);
}

void driveBackward(int speed = MOTOR_SPEED) {
  digitalWrite(MOTOR_A_IN1, LOW); digitalWrite(MOTOR_A_IN2, HIGH);
  digitalWrite(MOTOR_B_IN3, LOW); digitalWrite(MOTOR_B_IN4, HIGH);
  ledcWrite(0, speed);
  ledcWrite(1, speed);
}

void stopMotors() {
  digitalWrite(MOTOR_A_IN1, LOW); digitalWrite(MOTOR_A_IN2, LOW);
  digitalWrite(MOTOR_B_IN3, LOW); digitalWrite(MOTOR_B_IN4, LOW);
  ledcWrite(0, 0);
  ledcWrite(1, 0);
}

// ── LED helpers ─────────────────────────────────────────────────────────────
void setLED(bool r, bool g, bool b) {
  digitalWrite(LED_R, r ? HIGH : LOW);
  digitalWrite(LED_G, g ? HIGH : LOW);
  digitalWrite(LED_B, b ? HIGH : LOW);
}

// ── JSON messaging ─────────────────────────────────────────────────────────
void sendStatus(const char* state) {
  StaticJsonDocument<128> doc;
  doc["type"]  = "status";
  doc["state"] = state;
  serializeJson(doc, Serial2);
  Serial2.println();
}

void sendArrived(const char* player) {
  StaticJsonDocument<128> doc;
  doc["type"]   = "arrived";
  doc["player"] = player;
  serializeJson(doc, Serial2);
  Serial2.println();
}

// ── Command handling ───────────────────────────────────────────────────────
void handleCommand(const char* json) {
  StaticJsonDocument<256> doc;
  DeserializationError err = deserializeJson(doc, json);
  if (err) return;

  const char* type = doc["type"] | "";

  if (strcmp(type, "move") == 0) {
    const char* player = doc["player"] | "human";
    strncpy(targetPlayer, player, sizeof(targetPlayer) - 1);
    cartState = (strcmp(player, "human") == 0) ? MOVING_TO_HUMAN : MOVING_TO_AI;
    setLED(false, false, true);  // blue = moving
    sendStatus("moving");
    if (cartState == MOVING_TO_HUMAN) driveForward();
    else                              driveBackward();
  }
  else if (strcmp(type, "stop") == 0) {
    stopMotors();
    cartState = IDLE;
    setLED(false, true, false);  // green = idle
    sendStatus("idle");
  }
  else if (strcmp(type, "home") == 0) {
    // Drive backward until human sensor triggers
    cartState = MOVING_TO_HUMAN;
    strncpy(targetPlayer, "human", sizeof(targetPlayer) - 1);
    driveForward();
    setLED(false, false, true);
    sendStatus("moving");
  }
}

// ── Sensor check ───────────────────────────────────────────────────────────
void checkSensors() {
  if (cartState == IDLE) return;

  bool humanTriggered = (digitalRead(SENSOR_HUMAN) == LOW);
  bool aiTriggered    = (digitalRead(SENSOR_AI)    == LOW);

  if (cartState == MOVING_TO_HUMAN && humanTriggered) {
    stopMotors();
    cartState = IDLE;
    setLED(false, true, false);
    sendArrived("human");
    sendStatus("arrived");
  }
  else if (cartState == MOVING_TO_AI && aiTriggered) {
    stopMotors();
    cartState = IDLE;
    setLED(false, true, false);
    sendArrived("ai");
    sendStatus("arrived");
  }
}

// ── Setup / Loop ───────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);   // debug
  Serial2.begin(9600, SERIAL_8N1, 16, 17);  // communication with RPi/PC

  motorSetup();

  pinMode(SENSOR_HUMAN, INPUT_PULLUP);
  pinMode(SENSOR_AI,    INPUT_PULLUP);
  pinMode(LED_R, OUTPUT);
  pinMode(LED_G, OUTPUT);
  pinMode(LED_B, OUTPUT);

  setLED(false, true, false);  // green = ready
  stopMotors();
  sendStatus("idle");
  Serial.println("Tile cart ready");
}

void loop() {
  // Read incoming serial line from main computer
  static char rxBuf[256];
  static int  rxPos = 0;

  while (Serial2.available()) {
    char ch = Serial2.read();
    if (ch == '\n' || ch == '\r') {
      if (rxPos > 0) {
        rxBuf[rxPos] = '\0';
        handleCommand(rxBuf);
        rxPos = 0;
      }
    } else if (rxPos < (int)sizeof(rxBuf) - 1) {
      rxBuf[rxPos++] = ch;
    }
  }

  checkSensors();
  delay(10);
}
