const mqtt = require("mqtt");

// Change to your MQTT broker IP
const client = mqtt.connect("mqtt://192.168.1.23:1883");

console.log("🚀 Starting MQTT LED Controller...");

client.on("connect", () => {
  console.log("✅ Connected to MQTT Broker!");

  let isOn = false;

  // Function to toggle LED state
  const toggleLED = () => {
    isOn = !isOn;
    const state = isOn ? "ON" : "OFF";
    console.log(`📤 Publishing: esp32/led → ${state}`);
    client.publish("esp32/led", state);
  };

  // Start the loop - toggle every 3 seconds
  toggleLED(); // Initial publish
  setInterval(toggleLED, 3000);
});

client.on("reconnect", () => {
  console.log("🔄 Reconnecting to MQTT broker...");
});

client.on("error", (err) => {
  console.log("❌ MQTT Error:", err.message);
});

client.on("offline", () => {
  console.log("⚠️ MQTT Client is offline");
});

client.on("close", () => {
  console.log("🔌 Connection closed");
});
