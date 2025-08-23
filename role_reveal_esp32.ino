#include <WiFi.h>
#include <HTTPClient.h>
#include <SPI.h>
#include <MFRC522.h>
#include <LiquidCrystal_I2C.h>

// --------- WiFi Setup ----------
const char* ssid = "YourWiFiSSID";
const char* password = "YourWiFiPassword";

// --------- Server Setup ----------
const char* serverURL = "http://192.168.196.222:8000/role/"; // change to your server

// --------- LCD Setup ----------
LiquidCrystal_I2C lcd(0x27, 16, 2); // 16x2 LCD

// --------- RFID Setup ----------
#define RST_PIN 22
#define SS_PIN 21
MFRC522 mfrc522(SS_PIN, RST_PIN);

String lastUID = ""; // track currently displayed card

void setup() {
  Serial.begin(115200);
  SPI.begin();
  mfrc522.PCD_Init();

  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("Connecting WiFi");

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("WiFi Connected");
  delay(1000);
}

void loop() {
  // Check for new card presence
  if (!mfrc522.PICC_IsNewCardPresent() || !mfrc522.PICC_ReadCardSerial()) {
    // If no card, clear LCD or show default
    if (lastUID != "") {
      lcd.clear();
      lcd.setCursor(0, 0);
      lcd.print("Tap RFID Card");
      lastUID = "";
    }
    delay(500);
    return;
  }

  // Read card UID
  String uidStr = "";
  for (byte i = 0; i < mfrc522.uid.size; i++) {
    if (mfrc522.uid.uidByte[i] < 0x10) uidStr += "0";
    uidStr += String(mfrc522.uid.uidByte[i], HEX);
  }
  uidStr.toUpperCase();

  // Only fetch role if new card or first scan
  if (uidStr != lastUID) {
    lastUID = uidStr;
    fetchAndDisplayRole(uidStr);
  }

  // Keep displaying the same role while card is present
  delay(500);
}

void fetchAndDisplayRole(String rfid) {
  if (WiFi.status() != WL_CONNECTED) {
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("WiFi Lost");
    return;
  }

  HTTPClient http;
  String url = String(serverURL) + rfid;
  http.begin(url);
  int httpCode = http.GET();

  if (httpCode > 0) {
    String payload = http.getString();
    Serial.println("Role: " + payload);
    lcd.clear();
    if (payload.length() <= 16) {
      lcd.setCursor(0, 0);
      lcd.print(payload);
    } else {
      lcd.setCursor(0, 0);
      lcd.print(payload.substring(0, 16));
      lcd.setCursor(0, 1);
      lcd.print(payload.substring(16));
    }
  } else {
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("HTTP Error");
  }

  http.end();
}
