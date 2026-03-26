"""Quick test to check if the SDK can enumerate and create the Ferret device."""
import sys
sys.path.insert(0, r"C:\Python313\Lib\site-packages")

from pyorbbecsdk import *
import traceback

print("Creating context...")
ctx = Context()
print("Context created OK")

print("Querying device list...")
dev_list = ctx.query_devices()
count = dev_list.get_count()
print(f"Found {count} device(s)")

if count == 0:
    print("No devices found!")
    sys.exit(1)

for i in range(count):
    print(f"\nDevice {i}:")
    print(f"  Name: {dev_list.get_device_name_by_index(i)}")
    print(f"  PID:  0x{dev_list.get_device_pid_by_index(i):04X}")
    print(f"  VID:  0x{dev_list.get_device_vid_by_index(i):04X}")
    print(f"  SN:   {dev_list.get_device_serial_number_by_index(i)}")
    print(f"  Conn: {dev_list.get_device_connection_type_by_index(i)}")

print("\nOpening device 0...")
try:
    dev = dev_list.get_device_by_index(0)
    info = dev.get_device_info()
    print(f"  Name: {info.get_name()}")
    print(f"  FW:   {info.get_firmware_version()}")
    print(f"  SN:   {info.get_serial_number()}")
except Exception as e:
    print(f"  Failed to open device: {e}")
    traceback.print_exc()
    sys.exit(1)

print("\nGetting sensor list...")
try:
    sensor_list = dev.get_sensor_list()
    print(f"  Sensors: {sensor_list.get_count()}")
    for j in range(sensor_list.get_count()):
        sensor = sensor_list.get_sensor_by_index(j)
        print(f"    - {sensor.get_type()}")
except Exception as e:
    print(f"  Failed to get sensors: {e}")
    traceback.print_exc()

print("\nGetting stream profiles for depth sensor...")
try:
    depth_sensor = None
    for j in range(sensor_list.get_count()):
        s = sensor_list.get_sensor_by_index(j)
        if s.get_type() == OBSensorType.DEPTH_SENSOR:
            depth_sensor = s
            break
    if depth_sensor:
        profiles = depth_sensor.get_stream_profile_list()
        print(f"  Depth profiles: {profiles.get_count()}")
        for k in range(min(5, profiles.get_count())):
            p = profiles.get_stream_profile_by_index(k).as_video_stream_profile()
            print(f"    - {p.get_format()} {p.get_width()}x{p.get_height()} @{p.get_fps()}fps")
    else:
        print("  No depth sensor found!")
except Exception as e:
    print(f"  Failed: {e}")
    traceback.print_exc()

print("\nDone.")
