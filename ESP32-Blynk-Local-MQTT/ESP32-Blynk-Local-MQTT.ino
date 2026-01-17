#define BLYNK_TEMPLATE_ID             "TMPL6OE_pG3d1"
#define BLYNK_TEMPLATE_NAME           "MSE IoT ESP32"
#define BLYNK_FIRMWARE_VERSION        "0.1.0"

#define BLYNK_PRINT Serial
//#define BLYNK_DEBUG
#define APP_DEBUG

#include <WiFi.h>
#include <WiFiClient.h>
#include <PubSubClient.h>
#include "BlynkEdgent.h"

// ----------------- GPIO -----------------
#define AC_PIN  2
#define FAN_PIN 4

// ----------------- MQTT topic -----------------
static const char* TOPIC_CMD = "home/room1/actuator/cmd";

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

// ----------------- MQTT config (from Blynk) -----------------
static char mqttHost[64] = "<Your MQTT hostname or IP here>";     // default fallback
static uint16_t mqttPort = 1888;               // default fallback
static bool mqttConfigReady = false;           // becomes true when we have host+port

// ----------------- MQTT retry/disable logic -----------------
static bool mqttEnabled = true;
static uint8_t mqttFailCount = 0;
static const uint8_t MQTT_MAX_FAILS = 3;

// ----------------- Forward decl -----------------
void applyMqttServer();
void ensureMqttConnected();

// ----------------- Blynk handlers -----------------
BLYNK_WRITE(V0) {
  Serial.print("BLYNK_WRITE V0: ");
  Serial.println(param.asInt());
}
BLYNK_WRITE(V1) {
  Serial.print("BLYNK_WRITE V1: ");
  Serial.println(param.asInt());
}
BLYNK_WRITE(V2) {
  Serial.print("BLYNK_WRITE V2: ");
  Serial.println(param.asInt());
}

// V3: MQTT_HOST (String)
BLYNK_WRITE(V3) {
  String s = param.asString();
  s.trim();

  if (s.length() == 0) {
    Serial.println("[CFG] MQTT_HOST empty -> ignore");
    return;
  }
  if (s.length() >= (int)sizeof(mqttHost)) {
    Serial.println("[CFG] MQTT_HOST too long -> ignore");
    return;
  }

  s.toCharArray(mqttHost, sizeof(mqttHost));
  Serial.print("[CFG] MQTT_HOST set to: ");
  Serial.println(mqttHost);

  mqttConfigReady = true;
  mqttEnabled = true;          // re-enable if previously disabled
  mqttFailCount = 0;

  applyMqttServer();
}

// V4: MQTT_PORT (Integer)
BLYNK_WRITE(V4) {
  int p = param.asInt();
  if (p <= 0 || p > 65535) {
    Serial.println("[CFG] MQTT_PORT invalid -> ignore");
    return;
  }

  mqttPort = (uint16_t)p;
  Serial.print("[CFG] MQTT_PORT set to: ");
  Serial.println(mqttPort);

  mqttConfigReady = true;
  mqttEnabled = true;          // re-enable if previously disabled
  mqttFailCount = 0;

  applyMqttServer();
}
// Called when device connects to Blynk server
BLYNK_CONNECTED() {
  // Pull latest config values from server when online
  Serial.println("[Blynk] Connected -> syncing MQTT config (V3, V4)...");
  Blynk.syncVirtual(V3);
  Blynk.syncVirtual(V4);
}

// ----------------- MQTT callbacks -----------------
void onMqttMessage(char* topic, byte* payload, unsigned int length)
{
  Serial.print("[MQTT RX] ");
  Serial.print(topic);
  Serial.print(" -> ");

  String msg;
  msg.reserve(length + 1);
  for (unsigned int i = 0; i < length; i++) msg += (char)payload[i];
  Serial.println(msg);
}

// ----------------- MQTT server apply -----------------
void applyMqttServer()
{
  // (Re)configure MQTT server endpoint
  mqttClient.setServer(mqttHost, mqttPort);
  mqttClient.setCallback(onMqttMessage);

  // Drop current connection so next loop reconnects to new host/port
  if (mqttClient.connected()) {
    mqttClient.disconnect();
  }

  Serial.print("[MQTT] Server applied: ");
  Serial.print(mqttHost);
  Serial.print(":");
  Serial.println(mqttPort);
}

// ----------------- MQTT connect/reconnect -----------------
void ensureMqttConnected()
{
  if (!mqttEnabled) return;
  if (!mqttConfigReady) return;       // don't even try until we have config
  if (mqttClient.connected()) return;

  static uint32_t lastAttemptMs = 0;
  const uint32_t now = millis();
  if (now - lastAttemptMs < 3000) return; // attempt every 3s
  lastAttemptMs = now;

  String clientId = "esp32_actuator_";
  clientId += String((uint32_t)ESP.getEfuseMac(), HEX);

  Serial.print("[MQTT] Connecting to ");
  Serial.print(mqttHost);
  Serial.print(":");
  Serial.print(mqttPort);
  Serial.print(" as ");
  Serial.println(clientId);

  if (mqttClient.connect(clientId.c_str())) {
    Serial.println("[MQTT] Connected!");
    mqttFailCount = 0;
    mqttClient.subscribe(TOPIC_CMD);
    Serial.print("[MQTT] Subscribed: ");
    Serial.println(TOPIC_CMD);
  } else {
    mqttFailCount++;
    Serial.print("[MQTT] Connect failed, rc=");
    Serial.print(mqttClient.state());
    Serial.print(" (fail ");
    Serial.print(mqttFailCount);
    Serial.print("/");
    Serial.print(MQTT_MAX_FAILS);
    Serial.println(")");

    if (mqttFailCount >= MQTT_MAX_FAILS) {
      mqttEnabled = false;
      Serial.println("[MQTT] Disabled after 3 failed attempts. Blynk will continue.");
      mqttClient.disconnect();
    }
  }
}

void setup()
{
  pinMode(AC_PIN, OUTPUT);
  pinMode(FAN_PIN, OUTPUT);

  Serial.begin(115200);
  delay(100);

  BlynkEdgent.begin();

  // Default server config (fallback); will be overridden by Blynk if provided
  applyMqttServer();

  Serial.println("------");
  Serial.println("My ESP32 has started!");
}

void loop()
{
  BlynkEdgent.run();

  if (mqttEnabled) {
    ensureMqttConnected();
    mqttClient.loop();
  }

  delay(10);
}
