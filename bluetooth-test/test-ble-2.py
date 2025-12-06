#!/usr/bin/env python3
"""
BLE Counter Server for Raspberry Pi
This script creates a BLE GATT server that broadcasts a counter value.
When a button is pressed, the counter increments and notifies connected clients.

Uses bluez via dbus-python for BLE GATT server functionality.
"""

import dbus
import dbus.exceptions
import dbus.mainloop.glib
import dbus.service
import array
import sys
from gi.repository import GLib
import RPi.GPIO as GPIO
import threading
import time

# BLE Service UUID - You can generate your own UUIDs
SERVICE_UUID = "12345678-1234-1234-1234-123456789abc"
CHARACTERISTIC_UUID = "12345678-1234-1234-1234-123456789def"

# GPIO pin for button (using GPIO 18, adjust as needed)
BUTTON_PIN = 17

# Counter value
counter = 0
counter_lock = threading.Lock()

# D-Bus paths
BLUEZ_SERVICE_NAME = 'org.bluez'
GATT_MANAGER_IFACE = 'org.bluez.GattManager1'
DBUS_OM_IFACE = 'org.freedesktop.DBus.ObjectManager'
DBUS_PROP_IFACE = 'org.freedesktop.DBus.Properties'
GATT_SERVICE_IFACE = 'org.bluez.GattService1'
GATT_CHRC_IFACE = 'org.bluez.GattCharacteristic1'
GATT_DESC_IFACE = 'org.bluez.GattDescriptor1'
LE_ADVERTISING_MANAGER_IFACE = 'org.bluez.LEAdvertisingManager1'

class InvalidArgsException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.freedesktop.DBus.Error.InvalidArgs'

class NotSupportedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotSupported'

class NotPermittedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotPermitted'

class InvalidValueLengthException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.InvalidValueLength'

class FailedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.Failed'

class CounterCharacteristic(dbus.service.Object):
    """
    Counter Characteristic - exposes the counter value
    """
    
    def __init__(self, bus, index, service):
        self.path = service + '/char' + str(index)
        self.bus = bus
        self.chrc_flags = ['read', 'notify']
        dbus.service.Object.__init__(self, bus, self.path)
        self.add_service(service)
        self.notifying = False
        
    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                'Service': dbus.ObjectPath(self.service_path),
                'UUID': CHARACTERISTIC_UUID,
                'Flags': self.chrc_flags,
            }
        }
    
    def get_path(self):
        return dbus.ObjectPath(self.path)
    
    def add_service(self, service_path):
        self.service_path = service_path
    
    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_CHRC_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_CHRC_IFACE]
    
    @dbus.service.method(GATT_CHRC_IFACE,
                         in_signature='a{sv}',
                         out_signature='ay')
    def ReadValue(self, options):
        global counter
        with counter_lock:
            value = counter.to_bytes(4, byteorder='little', signed=False)
        print(f'ReadValue: Counter = {counter}')
        return dbus.Array(value, signature='y')
    
    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        if self.notifying:
            print('Already notifying')
            return
        self.notifying = True
        print('StartNotify')
    
    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        if not self.notifying:
            print('Not notifying')
            return
        self.notifying = False
        print('StopNotify')
    
    @dbus.service.signal(DBUS_PROP_IFACE,
                         signature='sa{sv}as')
    def PropertiesChanged(self, interface, changed, invalidated):
        pass
    
    def notify_counter_update(self):
        """Send notification to connected clients"""
        if not self.notifying:
            return
        global counter
        with counter_lock:
            value = counter.to_bytes(4, byteorder='little', signed=False)
        self.PropertiesChanged(
            GATT_CHRC_IFACE,
            {'Value': dbus.Array(value, signature='y')},
            []
        )

class CounterService(dbus.service.Object):
    """
    Counter Service - contains the counter characteristic
    """
    
    PATH_BASE = '/org/bluez/example/service'
    
    def __init__(self, bus, index):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        dbus.service.Object.__init__(self, bus, self.path)
    
    def get_properties(self):
        return {
            GATT_SERVICE_IFACE: {
                'UUID': SERVICE_UUID,
                'Primary': True,
                'Characteristics': dbus.Array([
                    self.characteristic.get_path()
                ], signature='o')
            }
        }
    
    def get_path(self):
        return dbus.ObjectPath(self.path)
    
    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_SERVICE_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_SERVICE_IFACE]
    
    def add_characteristic(self, characteristic):
        self.characteristic = characteristic

class Application(dbus.service.Object):
    """
    Main application object
    """
    
    def __init__(self, bus):
        self.path = '/'
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)
    
    def get_path(self):
        return dbus.ObjectPath(self.path)
    
    @dbus.service.method(DBUS_OM_IFACE, out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        response = {}
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            chrcs = service.characteristic.get_properties()
            response[service.characteristic.get_path()] = chrcs
        return response
    
    def add_service(self, service):
        self.services.append(service)

class CounterAdvertisement(dbus.service.Object):
    """
    Advertisement for the BLE service
    """
    
    PATH_BASE = '/org/bluez/example/advertisement'
    
    def __init__(self, bus, index, advertising_type):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.ad_type = advertising_type
        self.service_uuids = [SERVICE_UUID]
        self.manufacturer_data = None
        self.solicit_uuids = None
        self.service_data = None
        self.local_name = 'Raspberry Pi Counter'
        self.include_tx_power = None
        self.data = None
        dbus.service.Object.__init__(self, bus, self.path)
    
    def get_properties(self):
        properties = dict()
        properties['Type'] = self.ad_type
        if self.service_uuids is not None:
            properties['ServiceUUIDs'] = dbus.Array(self.service_uuids,
                                                     signature='s')
        if self.solicit_uuids is not None:
            properties['SolicitUUIDs'] = dbus.Array(self.solicit_uuids,
                                                     signature='s')
        if self.manufacturer_data is not None:
            properties['ManufacturerData'] = dbus.Dictionary(
                self.manufacturer_data, signature='qv')
        if self.service_data is not None:
            properties['ServiceData'] = dbus.Dictionary(self.service_data,
                                                        signature='sv')
        if self.local_name is not None:
            properties['LocalName'] = dbus.String(self.local_name)
        if self.include_tx_power is not None:
            properties['IncludeTxPower'] = dbus.Boolean(self.include_tx_power)
        if self.data is not None:
            properties['Data'] = dbus.Dictionary(self.data, signature='yv')
        return {LE_ADVERTISING_MANAGER_IFACE: properties}
    
    def get_path(self):
        return dbus.ObjectPath(self.path)
    
    def add_service_uuid(self, uuid):
        if not self.service_uuids:
            self.service_uuids = []
        self.service_uuids.append(uuid)
    
    def add_manufacturer_data(self, manuf_code, data):
        if not self.manufacturer_data:
            self.manufacturer_data = dbus.Dictionary({}, signature='qv')
        self.manufacturer_data[manuf_code] = dbus.Array(data, signature='y')
    
    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != LE_ADVERTISING_MANAGER_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[LE_ADVERTISING_MANAGER_IFACE]
    
    @dbus.service.method(LE_ADVERTISING_MANAGER_IFACE,
                         in_signature='',
                         out_signature='')
    def Release(self):
        print('%s: Released' % self.path)

# Global characteristic reference for notifications
characteristic_ref = None

def button_poll_thread():
    """Poll button state in a separate thread"""
    global counter, characteristic_ref
    
    last_state = GPIO.input(BUTTON_PIN)
    
    print(f"Button polling started on GPIO {BUTTON_PIN}")
    
    while True:
        try:
            current_state = GPIO.input(BUTTON_PIN)
            if current_state == GPIO.LOW and last_state == GPIO.HIGH:
                with counter_lock:
                    counter += 1
                    print(f"Button pressed! Counter: {counter}")
                
                # Notify connected clients about the counter update
                if characteristic_ref is not None:
                    characteristic_ref.notify_counter_update()
                
                time.sleep(0.3)  # Debounce delay
            last_state = current_state
            time.sleep(0.01)  # Small delay to prevent CPU spinning
        except Exception as e:
            print(f"Error in button polling: {e}")
            break

def register_ad_cb():
    print('Advertisement registered')

mainloop = None

def register_ad_error_cb(error):
    print(f'Failed to register advertisement: {error}')
    if mainloop:
        mainloop.quit()

def register_app_cb():
    print('GATT application registered')

def register_app_error_cb(error):
    print(f'Failed to register application: {error}')
    if mainloop:
        mainloop.quit()

def find_adapter(bus):
    """Find the first available BLE adapter"""
    remote_om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, '/'),
                                DBUS_OM_IFACE)
    objects = remote_om.GetManagedObjects()
    for o, props in objects.items():
        if LE_ADVERTISING_MANAGER_IFACE in props:
            return o
    return None

def main():
    global counter, characteristic_ref, mainloop
    
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    
    bus = dbus.SystemBus()
    
    # Find adapter
    adapter = find_adapter(bus)
    if not adapter:
        print('LEAdvertisingManager1 interface not found')
        return
    
    adapter_props = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter),
                                    DBUS_PROP_IFACE)
    adapter_props.Set('org.bluez.Adapter1', 'Powered', dbus.Boolean(1))
    
    # Setup GPIO for button
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    print(f"Button configured on GPIO {BUTTON_PIN}")
    
    # Start button polling thread
    button_thread = threading.Thread(target=button_poll_thread, daemon=True)
    button_thread.start()
    
    # Create application
    app = Application(bus)
    
    # Create service and characteristic
    service = CounterService(bus, 0)
    characteristic = CounterCharacteristic(bus, 0, service.path)
    characteristic_ref = characteristic
    service.add_characteristic(characteristic)
    app.add_service(service)
    
    # Register GATT application
    service_manager = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE_NAME, adapter),
        GATT_MANAGER_IFACE)
    service_manager.RegisterApplication(app.get_path(), {},
                                        reply_handler=register_app_cb,
                                        error_handler=register_app_error_cb)
    
    # Create and register advertisement
    ad_manager = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter),
                                 LE_ADVERTISING_MANAGER_IFACE)
    advertisement = CounterAdvertisement(bus, 0, 'peripheral')
    ad_manager.RegisterAdvertisement(advertisement.get_path(), {},
                                      reply_handler=register_ad_cb,
                                      error_handler=register_ad_error_cb)
    
    print("BLE Counter Server started!")
    print(f"Service UUID: {SERVICE_UUID}")
    print(f"Characteristic UUID: {CHARACTERISTIC_UUID}")
    print(f"Device name: Raspberry Pi Counter")
    print(f"Counter: {counter}")
    print("\nPress the button to increment the counter!")
    print("Press Ctrl+C to stop the server")
    
    mainloop = GLib.MainLoop()
    try:
        mainloop.run()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        GPIO.cleanup()
        print("Server stopped. GPIO cleaned up.")

if __name__ == '__main__':
    main()

