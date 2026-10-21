"""Test streaming color and IR from the Ferret."""
import sys, time
sys.path.insert(0, r"C:\Python313\Lib\site-packages")

from pyorbbecsdk import *

print("Opening device...")
ctx = Context()
dev_list = ctx.query_devices()
dev = dev_list.get_device_by_index(0)
info = dev.get_device_info()
print(f"  {info.get_name()} FW:{info.get_firmware_version()}")

# Try color stream
print("\nStarting color stream (MJPG 1280x720@30)...")
try:
    pipeline = Pipeline(dev)
    config = Config()

    color_profiles = pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
    print(f"  Color profiles: {color_profiles.get_count()}")

    # Find MJPG 1280x720
    color_profile = None
    for i in range(color_profiles.get_count()):
        p = color_profiles.get_stream_profile_by_index(i).as_video_stream_profile()
        if p.get_width() == 1280 and p.get_height() == 720 and p.get_format() == OBFormat.MJPG:
            color_profile = p
            print(f"  Found: {p.get_format()} {p.get_width()}x{p.get_height()} @{p.get_fps()}fps")
            break

    if color_profile:
        config.enable_stream(color_profile)
        pipeline.start(config)
        print("  Color stream started! Waiting for frames...")

        frame_count = 0
        start = time.time()
        while time.time() - start < 5:
            frames = pipeline.wait_for_frames(1000)
            if frames:
                color_frame = frames.get_color_frame()
                if color_frame:
                    frame_count += 1
                    if frame_count <= 3:
                        print(f"  Frame {frame_count}: {color_frame.get_width()}x{color_frame.get_height()} size={color_frame.get_data_size()}")

        print(f"  Got {frame_count} color frames in 5 seconds ({frame_count/5:.1f} fps)")
        pipeline.stop()
    else:
        print("  No suitable color profile found!")
except Exception as e:
    print(f"  Color stream failed: {e}")

print("\nDone.")
