#include <WiFi.h>
#include <HTTPClient.h>
#include <LiquidCrystal_I2C.h>

// --------- WiFi Setup ----------
const char* ssid = "YourWiFiSSID";
const char* password = "YourWiFiPassword";

// --------- Server Setup ----------
const char* serverURL = "http://192.168.196.222:8000/role/"; // change IP to your PC/server

// --------- LCD Setup ----------
LiquidCrystal_I2C lcd(0x27, 16, 2); // change 0x27 if your LCD has a different I2C address

// --------- Player ID ----------
String rfid = "P1"; // change for each card

void setup() {
  Serial.begin(115200);
  lcd.init();
  lcd.backlight();

  WiFi.begin(ssid, password);
  lcd.setCursor(0,0);
  lcd.print("Connecting WiFi");
  
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  lcd.clear();
  lcd.setCursor(0,0);
  lcd.print("WiFi Connected");
  delay(1000);
}

void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    String url = String(serverURL) + rfid;  // e.g., http://192.168.196.222:8000/role/P1
    http.begin(url);
    int httpCode = http.GET();

    if (httpCode > 0) {
      String payload = http.getString();
      Serial.println(payload);

      // Display on LCD
      lcd.clear();
      if (payload.length() <= 16) {
        lcd.setCursor(0,0);
        lcd.print(payload); // fits in one line
      } else {
        lcd.setCursor(0,0);
        lcd.print(payload.substring(0,16));
        lcd.setCursor(0,1);
        lcd.print(payload.substring(16));
      }

    } else {
      Serial.println("Error in HTTP request");
      lcd.clear();
      lcd.setCursor(0,0);
      lcd.print("HTTP Error");
    }

    http.end();
  } else {
    Serial.println("WiFi Disconnected");
    lcd.clear();
    lcd.setCursor(0,0);
    lcd.print("WiFi Lost");
  }

  delay(3000); // update every 3 seconds
}
