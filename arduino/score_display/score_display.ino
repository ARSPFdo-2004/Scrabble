/*
 * score_display.ino
 *
 * Arduino firmware for the Scrabble score display and challenge navigation.
 *
 * Hardware:
 *   - Arduino Mega / Uno
 *   - 20×4 I2C LCD display (address 0x27)
 *   - 3 navigation buttons: UP (pin 4), DOWN (pin 5), SELECT (pin 6)
 *   - Optional: buzzer on pin 7 for audio feedback
 *
 * Communication:
 *   - Serial (9600 baud) over USB to the Raspberry Pi / PC running the backend
 *   - Messages are newline-delimited JSON
 *
 * Outgoing JSON:
 *   {"type":"challenge","word":"<WORD>"}
 *   {"type":"navigate","direction":"up"|"down"|"select"}
 *
 * Incoming JSON:
 *   {"type":"scores","human":<n>,"ai":<n>}
 *   {"type":"words","words":["<W1>","<W2>",...]}
 *   {"type":"challenge_result","valid":<bool>,"word":"<W>","points":<n>}
 *   {"type":"turn","player":"human"|"ai"}
 */

#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <ArduinoJson.h>

// ── Pin definitions ───────────────────────────────────────────────────────
#define BTN_UP     4
#define BTN_DOWN   5
#define BTN_SELECT 6
#define BUZZER_PIN 7

// ── LCD ────────────────────────────────────────────────────────────────────
LiquidCrystal_I2C lcd(0x27, 20, 4);

// ── State ──────────────────────────────────────────────────────────────────
int  humanScore = 0;
int  aiScore    = 0;
char currentPlayer[8] = "human";

// Words available for challenge (up to 8 words)
#define MAX_WORDS 8
#define MAX_WORD_LEN 16
char  challengeWords[MAX_WORDS][MAX_WORD_LEN];
int   wordCount       = 0;
int   selectedWordIdx = 0;
bool  challengeMode   = false;

// Button debounce
unsigned long lastBtnTime = 0;
#define DEBOUNCE_MS 200

// ── Helpers ────────────────────────────────────────────────────────────────

void beep(int ms = 80) {
  digitalWrite(BUZZER_PIN, HIGH);
  delay(ms);
  digitalWrite(BUZZER_PIN, LOW);
}

void printLine(int row, const char* text) {
  lcd.setCursor(0, row);
  // Pad / truncate to 20 chars
  char buf[21];
  snprintf(buf, sizeof(buf), "%-20s", text);
  lcd.print(buf);
}

void renderScoreScreen() {
  char line[21];
  snprintf(line, sizeof(line), "Human: %5d", humanScore);
  printLine(0, line);
  snprintf(line, sizeof(line), "AI   : %5d", aiScore);
  printLine(1, line);
  snprintf(line, sizeof(line), "Turn : %-8s", currentPlayer);
  printLine(2, line);
  printLine(3, wordCount > 0 ? "SELECT=Challenge    " : "                    ");
}

void renderChallengeMenu() {
  printLine(0, "Challenge word?");
  char line[21];
  for (int i = 0; i < min(wordCount, 3); i++) {
    snprintf(line, sizeof(line), "%s%-16s",
             (i == selectedWordIdx) ? ">" : " ",
             challengeWords[i]);
    printLine(i + 1, line);
  }
}

void sendChallenge(const char* word) {
  StaticJsonDocument<128> doc;
  doc["type"] = "challenge";
  doc["word"] = word;
  serializeJson(doc, Serial);
  Serial.println();
  beep(150);
}

void sendNavigate(const char* dir) {
  StaticJsonDocument<64> doc;
  doc["type"]      = "navigate";
  doc["direction"] = dir;
  serializeJson(doc, Serial);
  Serial.println();
}

// ── Button handling ────────────────────────────────────────────────────────

void handleButtons() {
  unsigned long now = millis();
  if (now - lastBtnTime < DEBOUNCE_MS) return;

  bool up     = digitalRead(BTN_UP)     == LOW;
  bool down   = digitalRead(BTN_DOWN)   == LOW;
  bool select = digitalRead(BTN_SELECT) == LOW;

  if (!up && !down && !select) return;
  lastBtnTime = now;
  beep(50);

  if (!challengeMode) {
    if (select && wordCount > 0) {
      // Enter challenge mode
      challengeMode   = true;
      selectedWordIdx = 0;
      renderChallengeMenu();
    } else if (up)     sendNavigate("up");
    else if (down)     sendNavigate("down");
    return;
  }

  // Challenge mode navigation
  if (up) {
    selectedWordIdx = (selectedWordIdx - 1 + wordCount) % wordCount;
    renderChallengeMenu();
  } else if (down) {
    selectedWordIdx = (selectedWordIdx + 1) % wordCount;
    renderChallengeMenu();
  } else if (select) {
    // Confirm challenge
    sendChallenge(challengeWords[selectedWordIdx]);
    challengeMode = false;
    renderScoreScreen();
  }
}

// ── Serial message parsing ─────────────────────────────────────────────────

void handleIncoming(const char* json) {
  StaticJsonDocument<512> doc;
  DeserializationError err = deserializeJson(doc, json);
  if (err) return;

  const char* type = doc["type"] | "";

  if (strcmp(type, "scores") == 0) {
    humanScore = doc["human"] | 0;
    aiScore    = doc["ai"]    | 0;
    if (!challengeMode) renderScoreScreen();
  }
  else if (strcmp(type, "words") == 0) {
    wordCount = 0;
    JsonArray arr = doc["words"].as<JsonArray>();
    for (JsonVariant v : arr) {
      if (wordCount >= MAX_WORDS) break;
      strncpy(challengeWords[wordCount], v.as<const char*>(), MAX_WORD_LEN - 1);
      challengeWords[wordCount][MAX_WORD_LEN - 1] = '\0';
      wordCount++;
    }
    if (!challengeMode) renderScoreScreen();
  }
  else if (strcmp(type, "challenge_result") == 0) {
    bool  valid  = doc["valid"] | false;
    int   points = doc["points"] | 0;
    const char* word = doc["word"] | "";

    lcd.clear();
    printLine(0, "Challenge result:");
    printLine(1, word);
    char line[21];
    if (valid) {
      printLine(2, "VALID - You lose");
      printLine(3, "your turn");
    } else {
      snprintf(line, sizeof(line), "INVALID! +%d pts", points);
      printLine(2, line);
      printLine(3, "You WIN!");
    }
    beep(valid ? 100 : 300);
    delay(3000);
    renderScoreScreen();
  }
  else if (strcmp(type, "turn") == 0) {
    strncpy(currentPlayer, doc["player"] | "human", sizeof(currentPlayer) - 1);
    wordCount = 0;  // reset challengeable words on new turn
    if (!challengeMode) renderScoreScreen();
  }
}

// ── Setup / Loop ───────────────────────────────────────────────────────────

void setup() {
  Serial.begin(9600);
  Wire.begin();
  lcd.init();
  lcd.backlight();

  pinMode(BTN_UP,     INPUT_PULLUP);
  pinMode(BTN_DOWN,   INPUT_PULLUP);
  pinMode(BTN_SELECT, INPUT_PULLUP);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  lcd.clear();
  printLine(0, "  Scrabble v1.0  ");
  printLine(1, "  Score Display  ");
  printLine(2, "                 ");
  printLine(3, " Waiting for game");
  delay(2000);
  renderScoreScreen();
}

void loop() {
  // Read incoming serial line
  static char rxBuf[512];
  static int  rxPos = 0;

  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\n' || ch == '\r') {
      if (rxPos > 0) {
        rxBuf[rxPos] = '\0';
        handleIncoming(rxBuf);
        rxPos = 0;
      }
    } else if (rxPos < (int)sizeof(rxBuf) - 1) {
      rxBuf[rxPos++] = ch;
    }
  }

  handleButtons();
}
