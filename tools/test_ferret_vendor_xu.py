"""Test sending vendor XU stream enable commands via the SDK property system."""
import sys, time
sys.path.insert(0, r"C:\Python313\Lib\site-packages")

from pyorbbecsdk import *

print("Opening device...")
ctx = Context()
dev_list = ctx.query_devices()
dev = dev_list.get_device_by_index(0)
info = dev.get_device_info()
print(f"  {info.get_name()} FW:{info.get_firmware_version()}")

# The vendor XU property IDs from the handoff doc
PROP_STREAM_RESET = 0x0055   # Reset firmware stream state
PROP_DEPTH_ENABLE = 0x000E   # Enable depth processing
PROP_IR_ENABLE    = 0x0051   # Enable IR/color
PROP_STREAM_STOP  = 0x004D   # Stop stream
PROP_LASER_OFF    = 0x0003   # Laser off

# Try sending stream enable commands via set_int_property
print("\nSending vendor XU stream enable commands...")
for prop_id, prop_val, name in [
    (PROP_STREAM_RESET, 1, "Reset stream state (0x0055)"),
    (PROP_DEPTH_ENABLE, 1, "Enable depth (0x000E)"),
    (PROP_IR_ENABLE,    1, "Enable IR/color (0x0051)"),
]:
    try:
        dev.set_int_property(prop_id, prop_val)
        print(f"  OK: {name} = {prop_val}")
    except Exception as e:
        print(f"  FAIL: {name} = {prop_val} -> {e}")

print("\nWaiting 2s for projector warmup...")
time.sleep(2)

# Now try to start IR stream (simplest, no FrameProcessor needed)
print("\nStarting IR stream (Y8 1280x800@15)...")
try:
    sensor_list = dev.get_sensor_list()
    ir_sensor = None
    for j in range(sensor_list.get_count()):
        s = sensor_list.get_sensor_by_index(j)
        if s.get_type() == OBSensorType.IR_SENSOR:
            ir_sensor = s
            break

    if ir_sensor:
        profiles = ir_sensor.get_stream_profile_list()
        # Pick Y8 1280x800
        ir_profile = None
        for i in range(profiles.get_count()):
            p = profiles.get_stream_profile_by_index(i).as_video_stream_profile()
            if p.get_format() == OBFormat.Y8 and p.get_width() == 1280:
                ir_profile = profiles.get_stream_profile_by_index(i)
                print(f"  Using: {p.get_format()} {p.get_width()}x{p.get_height()} @{p.get_fps()}fps")
                break

        if ir_profile:
            pipeline = Pipeline(dev)
            config = Config()
            config.enable_stream(ir_profile)
            pipeline.start(config)
            print("  Stream started! Waiting for frames...")

            frame_count = 0
            start = time.time()
            while time.time() - start < 8:  # 8 seconds for projector warmup
                try:
                    frames = pipeline.wait_for_frames(1000)
                    if frames:
                        ir_frame = frames.get_ir_frame()
                        if ir_frame:
                            frame_count += 1
                            if frame_count <= 5:
                                data = ir_frame.get_data()
                                nonzero = sum(1 for b in data[:1000] if b != 0)
                                print(f"  Frame {frame_count}: {ir_frame.get_width()}x{ir_frame.get_height()} "
                                      f"size={ir_frame.get_data_size()} nonzero_first1k={nonzero}")
                except Exception as e:
                    print(f"  Frame error: {e}")

            print(f"  Got {frame_count} IR frames in 8s ({frame_count/8:.1f} fps)")

            # Send stop commands
            print("\nSending stream stop commands...")
            pipeline.stop()
            for prop_id, prop_val, name in [
                (PROP_STREAM_STOP, 1, "Stop stream (0x004D)"),
                (PROP_LASER_OFF,   0, "Laser off (0x0003)"),
            ]:
                try:
                    dev.set_int_property(prop_id, prop_val)
                    print(f"  OK: {name} = {prop_val}")
                except Exception as e:
                    print(f"  FAIL: {name} = {prop_val} -> {e}")
        else:
            print("  No Y8 1280x800 profile found!")
    else:
        print("  No IR sensor found!")
except Exception as e:
    print(f"  Stream failed: {e}")
    import traceback
    traceback.print_exc()

print("\nDone.")
