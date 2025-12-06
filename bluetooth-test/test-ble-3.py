import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib
import RPi.GPIO as GPIO
import threading
import time

SERVICE_UUID = "12345678-1234-1234-1234-123456789abc"
CHAR_UUID = "12345678-1234-1234-1234-123456789abd"
BUTTON_PIN = 17

BLUEZ_SERVICE_NAME = 'org.bluez'
GATT_MANAGER_IFACE = 'org.bluez.GattManager1'
DBUS_OM_IFACE = 'org.freedesktop.DBus.ObjectManager'
DBUS_PROP_IFACE = 'org.freedesktop.DBus.Properties'
GATT_SERVICE_IFACE = 'org.bluez.GattService1'
GATT_CHRC_IFACE = 'org.bluez.GattCharacteristic1'
LE_ADVERTISING_MANAGER_IFACE = 'org.bluez.LEAdvertisingManager1'

counter = 0
counter_lock = threading.Lock()
characteristic_ref = None

class InvalidArgsException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.freedesktop.DBus.Error.InvalidArgs'

class CounterCharacteristic(dbus.service.Object):
    def __init__(self, bus, index, service_path):
        self.path = service_path + '/char' + str(index)
        self.bus = bus
        self.service_path = service_path
        self.notifying = False
        dbus.service.Object.__init__(self, bus, self.path)
    
    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                'Service': dbus.ObjectPath(self.service_path),
                'UUID': CHAR_UUID,
                'Flags': ['read', 'notify'],
            }
        }
    
    def get_path(self):
        return dbus.ObjectPath(self.path)
    
    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_CHRC_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_CHRC_IFACE]
    
    @dbus.service.method(GATT_CHRC_IFACE, in_signature='a{sv}', out_signature='ay')
    def ReadValue(self, options):
        global counter
        with counter_lock:
            value = counter.to_bytes(4, byteorder='little', signed=False)
        return dbus.Array(value, signature='y')
    
    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        self.notifying = True
    
    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        self.notifying = False
    
    @dbus.service.signal(DBUS_PROP_IFACE, signature='sa{sv}as')
    def PropertiesChanged(self, interface, changed, invalidated):
        pass
    
    def notify_update(self):
        if not self.notifying:
            return
        global counter
        with counter_lock:
            value = counter.to_bytes(4, byteorder='little', signed=False)
        self.PropertiesChanged(GATT_CHRC_IFACE, {'Value': dbus.Array(value, signature='y')}, [])

class CounterService(dbus.service.Object):
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
                'Characteristics': dbus.Array([self.characteristic.get_path()], signature='o')
            }
        }
    
    def get_path(self):
        return dbus.ObjectPath(self.path)
    
    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_SERVICE_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_SERVICE_IFACE]
    
    def add_characteristic(self, characteristic):
        self.characteristic = characteristic

class Application(dbus.service.Object):
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
            response[service.characteristic.get_path()] = service.characteristic.get_properties()
        return response
    
    def add_service(self, service):
        self.services.append(service)

class CounterAdvertisement(dbus.service.Object):
    PATH_BASE = '/org/bluez/example/advertisement'
    
    def __init__(self, bus, index):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.service_uuids = [SERVICE_UUID]
        self.local_name = 'Raspberry Pi Counter'
        dbus.service.Object.__init__(self, bus, self.path)
    
    def get_properties(self):
        return {
            LE_ADVERTISING_MANAGER_IFACE: {
                'Type': 'peripheral',
                'ServiceUUIDs': dbus.Array(self.service_uuids, signature='s'),
                'LocalName': dbus.String(self.local_name),
            }
        }
    
    def get_path(self):
        return dbus.ObjectPath(self.path)
    
    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != LE_ADVERTISING_MANAGER_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[LE_ADVERTISING_MANAGER_IFACE]
    
    @dbus.service.method(LE_ADVERTISING_MANAGER_IFACE, in_signature='', out_signature='')
    def Release(self):
        pass

def button_poll():
    global counter, characteristic_ref
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    last_state = GPIO.input(BUTTON_PIN)
    
    while True:
        current_state = GPIO.input(BUTTON_PIN)
        if current_state == GPIO.LOW and last_state == GPIO.HIGH:
            with counter_lock:
                counter += 1
                print(f"Button pressed! Count: {counter}")
            if characteristic_ref:
                characteristic_ref.notify_update()
            time.sleep(0.3)
        last_state = current_state
        time.sleep(0.01)

def find_adapter(bus):
    remote_om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, '/'), DBUS_OM_IFACE)
    objects = remote_om.GetManagedObjects()
    for o, props in objects.items():
        if LE_ADVERTISING_MANAGER_IFACE in props:
            return o
    return None

def main():
    global characteristic_ref
    
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    
    adapter = find_adapter(bus)
    if not adapter:
        print('No BLE adapter found')
        return
    
    adapter_props = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter), DBUS_PROP_IFACE)
    adapter_props.Set('org.bluez.Adapter1', 'Powered', dbus.Boolean(1))
    
    app = Application(bus)
    service = CounterService(bus, 0)
    characteristic = CounterCharacteristic(bus, 0, service.path)
    characteristic_ref = characteristic
    service.add_characteristic(characteristic)
    app.add_service(service)
    
    service_manager = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter), GATT_MANAGER_IFACE)
    service_manager.RegisterApplication(
        app.get_path(),
        {},
        reply_handler=lambda: print('GATT registered'),
        error_handler=lambda e: print(f'Error: {e}')
    )
    
    ad_manager = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter), LE_ADVERTISING_MANAGER_IFACE)
    advertisement = CounterAdvertisement(bus, 0)
    ad_manager.RegisterAdvertisement(
        advertisement.get_path(),
        {},
        reply_handler=lambda: print('Advertisement registered'),
        error_handler=lambda e: print(f'Error: {e}')
    )
    
    threading.Thread(target=button_poll, daemon=True).start()
    
    print("BLE server started")
    print(f"Service UUID: {SERVICE_UUID}")
    print(f"Characteristic UUID: {CHAR_UUID}")
    
    mainloop = GLib.MainLoop()
    try:
        mainloop.run()
    except KeyboardInterrupt:
        GPIO.cleanup()

if __name__ == '__main__':
    main()
