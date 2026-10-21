"""Test listing profiles and streaming IR from the Ferret."""
import sys, time
sys.path.insert(0, r"C:\Python313\Lib\site-packages")

from pyorbbecsdk import *

print("Opening device...")
ctx = Context()
dev_list = ctx.query_devices()
dev = dev_list.get_device_by_index(0)
info = dev.get_device_info()
print(f"  {info.get_name()} FW:{info.get_firmware_version()}")

pipeline = Pipeline(dev)

# List all color profiles
print("\nColor profiles:")
try:
    profiles = pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
    for i in range(min(10, profiles.get_count())):
        p = profiles.get_stream_profile_by_index(i).as_video_stream_profile()
        print(f"  [{i}] {p.get_format()} {p.get_width()}x{p.get_height()} @{p.get_fps()}fps")
except Exception as e:
    print(f"  Failed: {e}")

# List IR profiles
print("\nIR profiles:")
try:
    profiles = pipeline.get_stream_profile_list(OBSensorType.IR_SENSOR)
    for i in range(min(10, profiles.get_count())):
        p = profiles.get_stream_profile_by_index(i).as_video_stream_profile()
        print(f"  [{i}] {p.get_format()} {p.get_width()}x{p.get_height()} @{p.get_fps()}fps")
except Exception as e:
    print(f"  Failed: {e}")

# Try starting IR stream
print("\nStarting IR stream...")
try:
    config = Config()
    ir_profiles = pipeline.get_stream_profile_list(OBSensorType.IR_SENSOR)
    # Pick first one
    ir_profile = ir_profiles.get_stream_profile_by_index(0)
    p = ir_profile.as_video_stream_profile()
    print(f"  Using: {p.get_format()} {p.get_width()}x{p.get_height()} @{p.get_fps()}fps")
    config.enable_stream(ir_profile)
    pipeline.start(config)
    print("  IR stream started! Waiting for frames...")

    frame_count = 0
    start = time.time()
    while time.time() - start < 5:
        frames = pipeline.wait_for_frames(1000)
        if frames:
            ir_frame = frames.get_ir_frame()
            if ir_frame:
                frame_count += 1
                if frame_count <= 3:
                    print(f"  Frame {frame_count}: {ir_frame.get_width()}x{ir_frame.get_height()} size={ir_frame.get_data_size()}")

    print(f"  Got {frame_count} IR frames in 5s ({frame_count/5:.1f} fps)")
    pipeline.stop()
except Exception as e:
    print(f"  IR stream failed: {e}")

print("\nDone.")
