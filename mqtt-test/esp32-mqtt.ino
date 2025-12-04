#include <WiFi.h>
#include <PubSubClient.h>

const char* ssid = "UBA_2.4G";
const char* password = "izhanhebat123";

const char* mqtt_server = "192.168.1.23"; // your broker IP
const int ledPin = 2;

WiFiClient espClient;
PubSubClient client(espClient);

void callback(char* topic, byte* message, unsigned int length) {
  String msg;
  for (int i = 0; i < length; i++) {
    msg += (char)message[i];
  }

  Serial.println("MQTT Message received: " + msg);

  if (msg == "ON") digitalWrite(ledPin, HIGH);
  if (msg == "OFF") digitalWrite(ledPin, LOW);
}

void connectWiFi() {
  Serial.println();
  Serial.println("Connecting to WiFi...");
  WiFi.begin(ssid, password);

  int retryCount = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    retryCount++;

    if (retryCount >= 20) { // ~10 seconds timeout
      Serial.println("\n⚠️ WiFi connection failed. Retrying...");
      WiFi.disconnect();
      delay(2000);
      WiFi.begin(ssid, password);
      retryCount = 0;
    }
  }

  Serial.println("\n✅ WiFi Connected!");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());
}

void reconnectMQTT() {
  while (!client.connected()) {
    Serial.println("Connecting to MQTT...");
    if (client.connect("ESP32Client")) {
      Serial.println("✅ MQTT Connected!");
      client.subscribe("esp32/led");
    } else {
      Serial.print("❌ MQTT Failed, rc=");
      Serial.print(client.state());
      Serial.println(" — retrying in 2 seconds...");
      delay(2000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(ledPin, OUTPUT);

  connectWiFi();

  client.setServer(mqtt_server, 1883);
  client.setCallback(callback);
}

void loop() {
  if (!client.connected()) reconnectMQTT();
  client.loop();
}
