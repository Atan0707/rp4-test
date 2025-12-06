import paho.mqtt.client as mqtt
import random
import string
from paho.mqtt.client import CallbackAPIVersion

def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code = 0;
        print("Connected successfully")
    else:
        print(f"Connection failed with reason {reason_code}")

def on_message(client)