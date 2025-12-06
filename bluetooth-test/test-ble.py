# python3 -m venv venv --system-site-packages
# source venv/bin/activate
# pip install -r requirements.txt

import RPi.GPIO as GPIO
import time
import dbus
import dbus.exceptions
import dbus.mainloop.glib
import dbus.service
import array
from gi.repository import GLib
import threading

# Bluetooth configuration
SERVICE_UUID = "00001848-0000-1000-8000-00805f9b34fb"
CHARACTERISTIC_UUID = "00002a6f-0000-1000-8000-00805f9b34fb"  # Read/Notify characteristic
BLE_NAME = "RP4-Button"

# GPIO configuration
BUTTON_PIN = 17
counter = 0
last_state = GPIO.HIGH

# D-Bus configuration
BLUEZ_SERVICE_NAME = "org.bluez"
GATT_MANAGER_IFACE = "org.bluez.GattManager1"
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"
DBUS_PROP_IFACE = "org.freedesktop.DBus.Properties"
GATT_SERVICE_IFACE = "org.bluez.GattService1"
GATT_CHRC_IFACE = "org.bluez.GattCharacteristic1"
GATT_DESC_IFACE = "org.bluez.GattDescriptor1"

class InvalidArgsException(dbus.exceptions.DBusException):
    _dbus_error_name = "org.freedesktop.DBus.Error.InvalidArgs"

class NotSupportedException(dbus.exceptions.DBusException):
    _dbus_error_name = "org.bluez.Error.NotSupported"

class NotPermittedException(dbus.exceptions.DBusException):
    _dbus_error_name = "org.bluez.Error.NotPermitted"

class InvalidValueLengthException(dbus.exceptions.DBusException):
    _dbus_error_name = "org.bluez.Error.InvalidValueLength"

class FailedException(dbus.exceptions.DBusException):
    _dbus_error_name = "org.bluez.Error.Failed"

class Application(dbus.service.Object):
    def __init__(self, bus):
        self.path = "/"
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service(self, service):
        self.services.append(service)

    @dbus.service.method(DBUS_OM_IFACE, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        response = {}
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            chrcs = service.get_characteristics()
            for chrc in chrcs:
                response[chrc.get_path()] = chrc.get_properties()
        return response

class Service(dbus.service.Object):
    PATH_BASE = "/org/bluez/example/service"

    def __init__(self, bus, index, uuid, primary):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.uuid = uuid
        self.primary = primary
        self.characteristics = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_SERVICE_IFACE: {
                "UUID": self.uuid,
                "Primary": self.primary,
                "Characteristics": dbus.Array(
                    self.get_characteristic_paths(), signature="o"
                ),
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_characteristic(self, characteristic):
        self.characteristics.append(characteristic)

    def get_characteristics(self):
        return self.characteristics

    def get_characteristic_paths(self):
        result = []
        for chrc in self.characteristics:
            result.append(chrc.get_path())
        return result

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != GATT_SERVICE_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_SERVICE_IFACE]

class Characteristic(dbus.service.Object):
    def __init__(self, bus, index, uuid, flags, service):
        self.path = service.path + "/char" + str(index)
        self.bus = bus
        self.uuid = uuid
        self.service = service
        self.flags = flags
        self.value = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                "Service": self.service.get_path(),
                "UUID": self.uuid,
                "Flags": self.flags,
                "Value": dbus.Array(self.value, signature="y"),
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != GATT_SERVICE_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_CHRC_IFACE]

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="a{sv}", out_signature="ay")
    def ReadValue(self, options):
        return self.value

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="aya{sv}")
    def WriteValue(self, value, options):
        self.value = value

    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        pass

    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        pass

    def update_value(self, value):
        if not self.value == value:
            self.value = value
            self.PropertiesChanged(
                GATT_CHRC_IFACE, {"Value": dbus.Array(self.value, signature="y")}, []
            )

class ButtonCharacteristic(Characteristic):
    def __init__(self, bus, index, service):
        Characteristic.__init__(
            self, bus, index, CHARACTERISTIC_UUID, ["read", "notify"], service
        )
        self.notifying = False

    def update_counter(self, count):
        message = f"Count: {count}"
        value = [dbus.Byte(c) for c in message.encode("utf-8")]
        self.update_value(value)

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="a{sv}", out_signature="ay")
    def ReadValue(self, options):
        message = f"Count: {counter}"
        return [dbus.Byte(c) for c in message.encode("utf-8")]

    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        if self.notifying:
            return
        self.notifying = True

    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        if not self.notifying:
            return
        self.notifying = False

def register_app_cb():
    print("GATT application registered")

def register_app_error_cb(error):
    print(f"Failed to register application: {error}")

def button_monitor(characteristic):
    global counter, last_state
    
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    last_state = GPIO.input(BUTTON_PIN)
    
    print(f"Monitoring GPIO pin {BUTTON_PIN} for button presses...")
    
    try:
        while True:
            current_state = GPIO.input(BUTTON_PIN)
            if current_state == GPIO.LOW and last_state == GPIO.HIGH:
                counter += 1
                print(f"Button pressed! Count: {counter}")
                characteristic.update_counter(counter)
                time.sleep(0.3)  # Debounce delay
            last_state = current_state
            time.sleep(0.01)
    except KeyboardInterrupt:
        GPIO.cleanup()

def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    
    # Get adapter
    adapter = None
    adapter_path = None
    om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, "/"), DBUS_OM_IFACE)
    objects = om.GetManagedObjects()
    
    for path, interfaces in objects.items():
        if GATT_MANAGER_IFACE in interfaces:
            adapter = dbus.Interface(
                bus.get_object(BLUEZ_SERVICE_NAME, path), GATT_MANAGER_IFACE
            )
            adapter_path = path
            break
    
    if not adapter:
        print("No BLE adapter found")
        return
    
    # Create application
    app = Application(bus)
    service = Service(bus, 0, SERVICE_UUID, True)
    characteristic = ButtonCharacteristic(bus, 0, service)
    service.add_characteristic(characteristic)
    app.add_service(service)
    
    # Register application
    adapter.RegisterApplication(
        app.get_path(),
        {},
        reply_handler=register_app_cb,
        error_handler=register_app_error_cb,
    )
    
    # Start button monitoring in separate thread
    button_thread = threading.Thread(target=button_monitor, args=(characteristic,))
    button_thread.daemon = True
    button_thread.start()
    
    print(f"BLE Peripheral '{BLE_NAME}' started")
    print("Waiting for connections...")
    
    try:
        mainloop = GLib.MainLoop()
        mainloop.run()
    except KeyboardInterrupt:
        print(f"\nTotal button presses: {counter}")
        GPIO.cleanup()
        adapter.UnregisterApplication(app.get_path())

if __name__ == "__main__":
    main()
