#include <WiFi.h>
#include <HTTPClient.h>
#include <SPI.h>
#include <MFRC522.h>

#define WIFI_SSID "Bluebob"
#define WIFI_PASS "takeitok"
String SERVER_URL = "http://192.168.146.55:8000";  // replace with your server IP

#define RST_PIN 22
#define SS_PIN 21

MFRC522 mfrc522(SS_PIN, RST_PIN);

// 🔹 Fixed player ID and color for this ESP32
String playerId = "PLAYER1";   // <-- change for each device
String playerColor = "Red";    // <-- change for each device

void setup() {
  Serial.begin(115200);
  SPI.begin();
  mfrc522.PCD_Init();

  connectWiFi();

  // Register this player with server (retry until success)
  registerWithServer(playerId, playerColor);
}

void loop() {
  // Ensure WiFi stays connected
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi disconnected! Reconnecting...");
    connectWiFi();
  }

  // Wait for RFID scan
  if (!mfrc522.PICC_IsNewCardPresent() || !mfrc522.PICC_ReadCardSerial())
    return;

  // Get scanned RFID (impostor)
  String impostor = "";
  for (byte i = 0; i < mfrc522.uid.size; i++) {
    if (mfrc522.uid.uidByte[i] < 0x10) impostor += "0"; // leading zero
    impostor += String(mfrc522.uid.uidByte[i], HEX);
  }

  impostor.toUpperCase();

  Serial.println("Scanned impostor card: " + impostor);

  // Try to kill THIS player (with retries)
  doKill(impostor, playerId);

  delay(1000);
}

// ---------------------------
// WiFi Helper
// ---------------------------
void connectWiFi() {
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting to WiFi");
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) { // ~10s timeout
    delay(500);
    Serial.print(".");
    attempts++;
  }
  if (WiFi.status() == WL_CONNECTED)
    Serial.println("\nConnected to WiFi");
  else
    Serial.println("\nWiFi connect failed!");
}

// ---------------------------
// API Functions
// ---------------------------
// Convert impostor to uppercase and fix connect URL
//impostor = impostor.toUpperCase();

// Register function
void registerWithServer(String rfid, String color) {
  bool success = false;

  while (!success) {
    if (WiFi.status() != WL_CONNECTED) connectWiFi();

    HTTPClient http;
    http.begin(SERVER_URL + "/connect/" + rfid + "/" + color);  // ✅ path params
    int httpCode = http.GET();
    if (httpCode == 200) {
      String payload = http.getString();
      Serial.println("✅ Player registered with server: " + rfid + " | " + color);
      Serial.println(payload);
      success = true;
    } else {
      Serial.println("❌ Failed to register player, retrying in 3s...");
      delay(3000);
    }
    http.end();
  }
}

// Kill function
void doKill(String impostor, String target) {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();

  bool success = false;
  int retries = 3;

  for (int i = 0; i < retries && !success; i++) {
    HTTPClient http;
    http.begin(SERVER_URL + "/kill/" + impostor + "/" + target);
    http.addHeader("Content-Type", "application/json");
    int httpCode = http.POST("{}");  // ✅ empty JSON
    if (httpCode == 200) {
      String payload = http.getString();
      Serial.println("Kill result: " + payload);
      success = true;
    } else {
      Serial.println("Kill request failed (attempt " + String(i+1) + ")");
      delay(1000);
      if (WiFi.status() != WL_CONNECTED) connectWiFi();
    }
    http.end();
  }

  if (!success) Serial.println("❌ Kill request ultimately failed after retries.");
}
