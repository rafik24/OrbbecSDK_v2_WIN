"""CR-Scan Ferret — all streams viewer with IMU data.
Shows Color, Depth (colorized Y16), IR, and IMU in a 2x2 grid.
Uses Pipeline for synchronized color+depth+IR, separate pipeline for IMU.

Keys: q=quit, m=toggle IR mirror
"""
import sys, time, threading
sys.path.insert(0, r"C:\Python313\Lib\site-packages")

from pyorbbecsdk import *
import numpy as np
import cv2

# ── Open device ──────────────────────────────────────────────────────
ctx = Context()
dl = ctx.query_devices()
if dl.get_count() == 0:
    print("No devices found!")
    sys.exit(1)

dev = dl.get_device_by_index(0)
info = dev.get_device_info()
print(f"Device: {info.get_name()} FW:{info.get_firmware_version()} SN:{info.get_serial_number()}")

sl = dev.get_sensor_list()
sensors = {}
for j in range(sl.get_count()):
    s = sl.get_sensor_by_index(j)
    sensors[s.get_type()] = s
    print(f"  Sensor: {s.get_type()}")

# ── Find profiles ────────────────────────────────────────────────────
def find_profile(sensor, fmt=None, w=None, h=None, fps=None):
    profiles = sensor.get_stream_profile_list()
    for i in range(profiles.get_count()):
        p = profiles.get_stream_profile_by_index(i).as_video_stream_profile()
        if fmt and p.get_format() != fmt:
            continue
        if w and p.get_width() != w:
            continue
        if h and p.get_height() != h:
            continue
        if fps and p.get_fps() != fps:
            continue
        return profiles.get_stream_profile_by_index(i)
    return profiles.get_stream_profile_by_index(0)

# ── Shared state ─────────────────────────────────────────────────────
lock = threading.Lock()
imu_data = {"accel": None, "gyro": None}
stop_event = threading.Event()

# ── IMU thread ───────────────────────────────────────────────────────
def imu_thread_fn():
    try:
        accel_sensor = sensors.get(OBSensorType.ACCEL_SENSOR)
        gyro_sensor = sensors.get(OBSensorType.GYRO_SENSOR)
        if not accel_sensor or not gyro_sensor:
            return

        accel_profiles = accel_sensor.get_stream_profile_list()
        gyro_profiles = gyro_sensor.get_stream_profile_list()

        imu_pipeline = Pipeline(dev)
        imu_config = Config()
        imu_config.enable_stream(accel_profiles.get_stream_profile_by_index(0))
        imu_config.enable_stream(gyro_profiles.get_stream_profile_by_index(0))
        imu_pipeline.start(imu_config)

        while not stop_event.is_set():
            try:
                frames = imu_pipeline.wait_for_frames(100)
                if frames:
                    try:
                        af = frames.get_frame(OBFrameType.ACCEL_FRAME)
                        if af:
                            with lock:
                                imu_data["accel"] = af.as_accel_frame().get_value()
                    except:
                        pass
                    try:
                        gf = frames.get_frame(OBFrameType.GYRO_FRAME)
                        if gf:
                            with lock:
                                imu_data["gyro"] = gf.as_gyro_frame().get_value()
                    except:
                        pass
            except:
                pass
        imu_pipeline.stop()
    except Exception as e:
        print(f"IMU thread error: {e}")

imu_t = threading.Thread(target=imu_thread_fn, daemon=True)
imu_t.start()

# ── Video pipeline ───────────────────────────────────────────────────
pipeline = Pipeline(dev)
config = Config()

if OBSensorType.COLOR_SENSOR in sensors:
    color_profile = find_profile(sensors[OBSensorType.COLOR_SENSOR], OBFormat.MJPG, 1280, 720)
    p = color_profile.as_video_stream_profile()
    print(f"Color: {p.get_format()} {p.get_width()}x{p.get_height()} @{p.get_fps()}fps")
    config.enable_stream(color_profile)

if OBSensorType.DEPTH_SENSOR in sensors:
    depth_profile = find_profile(sensors[OBSensorType.DEPTH_SENSOR], OBFormat.Y16, 1280, 800)
    p = depth_profile.as_video_stream_profile()
    if p.get_format() != OBFormat.Y16:
        depth_profile = find_profile(sensors[OBSensorType.DEPTH_SENSOR], OBFormat.Y14, 1280, 800)
        p = depth_profile.as_video_stream_profile()
    print(f"Depth: {p.get_format()} {p.get_width()}x{p.get_height()} @{p.get_fps()}fps")
    config.enable_stream(depth_profile)

if OBSensorType.IR_SENSOR in sensors:
    ir_profile = find_profile(sensors[OBSensorType.IR_SENSOR], OBFormat.Y8, 1280, 800)
    p = ir_profile.as_video_stream_profile()
    print(f"IR:    {p.get_format()} {p.get_width()}x{p.get_height()} @{p.get_fps()}fps")
    config.enable_stream(ir_profile)

pipeline.start(config)
print("All streams started. Press 'q' to quit, 'm' to toggle IR mirror.")
time.sleep(2)

ir_mirror = True
frame_count = 0
fps_start = time.time()
fps_val = 0
TILE_W, TILE_H = 640, 400

while True:
    try:
        frames = pipeline.wait_for_frames(100)
    except:
        continue

    if frames:
        frame_count += 1

    elapsed = time.time() - fps_start
    if elapsed >= 1.0:
        fps_val = frame_count / elapsed
        frame_count = 0
        fps_start = time.time()

    # ── Color ─────────────────────────────────────────────────────
    color_img = np.zeros((TILE_H, TILE_W, 3), dtype=np.uint8)
    if frames:
        cf = frames.get_color_frame()
        if cf:
            try:
                data = np.frombuffer(cf.get_data(), dtype=np.uint8)
                img = cv2.imdecode(data, cv2.IMREAD_COLOR)
                if img is not None:
                    color_img = cv2.resize(img, (TILE_W, TILE_H))
            except:
                pass
    cv2.putText(color_img, "Color (MJPG 1280x720)", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    # ── Depth ─────────────────────────────────────────────────────
    depth_img = np.zeros((TILE_H, TILE_W, 3), dtype=np.uint8)
    if frames:
        df = frames.get_depth_frame()
        if df:
            try:
                depth16 = np.frombuffer(df.get_data(), dtype=np.uint16)
                w, h = df.get_width(), df.get_height()
                if depth16.size >= w * h:
                    depth_map = depth16[:w * h].reshape((h, w))
                    depth_clipped = np.clip(depth_map, 0, 5000)
                    depth_norm = cv2.normalize(depth_clipped, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                    depth_img = cv2.applyColorMap(depth_norm, cv2.COLORMAP_JET)
                    depth_img[depth_map == 0] = [0, 0, 0]
                    depth_img = cv2.resize(depth_img, (TILE_W, TILE_H))
                    valid = depth_map[depth_map > 0]
                    if valid.size > 0:
                        cv2.putText(depth_img, f"min={valid.min()}mm max={valid.max()}mm",
                                    (10, TILE_H - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
            except:
                pass
    cv2.putText(depth_img, "Depth (Y16 1280x800)", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    # ── IR ────────────────────────────────────────────────────────
    ir_img = np.zeros((TILE_H, TILE_W, 3), dtype=np.uint8)
    if frames:
        irf = frames.get_ir_frame()
        if irf:
            try:
                data = np.frombuffer(irf.get_data(), dtype=np.uint8)
                w, h = irf.get_width(), irf.get_height()
                if data.size >= w * h:
                    gray = data[:w * h].reshape((h, w))
                    if ir_mirror:
                        gray = cv2.flip(gray, 1)
                    gray = cv2.equalizeHist(gray)
                    ir_img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
                    ir_img = cv2.resize(ir_img, (TILE_W, TILE_H))
            except:
                pass
    mirror_str = "mirrored" if ir_mirror else "normal"
    cv2.putText(ir_img, f"IR (Y8 1280x800) [{mirror_str}]", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    # ── IMU panel ─────────────────────────────────────────────────
    imu_img = np.zeros((TILE_H, TILE_W, 3), dtype=np.uint8)
    cv2.putText(imu_img, "IMU Data", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

    with lock:
        accel = imu_data["accel"]
        gyro = imu_data["gyro"]

    y = 80
    if accel:
        cv2.putText(imu_img, f"Accel X: {accel.x:+8.3f} m/s2", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        cv2.putText(imu_img, f"Accel Y: {accel.y:+8.3f} m/s2", (10, y+25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        cv2.putText(imu_img, f"Accel Z: {accel.z:+8.3f} m/s2", (10, y+50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        magnitude = (accel.x**2 + accel.y**2 + accel.z**2)**0.5
        cv2.putText(imu_img, f"|A| = {magnitude:.2f} m/s2", (10, y+80), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)
    else:
        cv2.putText(imu_img, "Accel: waiting...", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)

    y = 220
    if gyro:
        cv2.putText(imu_img, f"Gyro  X: {gyro.x:+8.3f} dps", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        cv2.putText(imu_img, f"Gyro  Y: {gyro.y:+8.3f} dps", (10, y+25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        cv2.putText(imu_img, f"Gyro  Z: {gyro.z:+8.3f} dps", (10, y+50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    else:
        cv2.putText(imu_img, "Gyro: waiting...", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)

    cv2.putText(imu_img, f"FPS: {fps_val:.1f}", (10, 340), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
    cv2.putText(imu_img, f"{info.get_name()} FW:{info.get_firmware_version()}", (10, 370),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)
    cv2.putText(imu_img, f"SN: {info.get_serial_number()}  [q]uit [m]irror", (10, 390),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)

    # ── Compose 2x2 grid ─────────────────────────────────────────
    top = np.hstack([color_img, depth_img])
    bottom = np.hstack([ir_img, imu_img])
    canvas = np.vstack([top, bottom])

    cv2.imshow("CR-Scan Ferret - All Streams", canvas)
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q') or key == 27:
        break
    elif key == ord('m'):
        ir_mirror = not ir_mirror
        print(f"IR mirror: {ir_mirror}")

# ── Cleanup ──────────────────────────────────────────────────────────
stop_event.set()
pipeline.stop()
imu_t.join(timeout=2)
cv2.destroyAllWindows()
print("Done.")
