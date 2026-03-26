"""CR-Scan Ferret — all streams viewer with IMU data.
Uses separate sensor start/callback for each stream to avoid pipeline sync issues."""
import sys, time, threading
sys.path.insert(0, r"C:\Python313\Lib\site-packages")

from pyorbbecsdk import *
import numpy as np
import cv2

# ── Open device ──────────────────────────────────────────────────────
ctx = Context()
dl = ctx.query_devices()
dev = dl.get_device_by_index(0)
info = dev.get_device_info()
print(f"Device: {info.get_name()} FW:{info.get_firmware_version()} SN:{info.get_serial_number()}")

sl = dev.get_sensor_list()
sensors = {}
for j in range(sl.get_count()):
    s = sl.get_sensor_by_index(j)
    sensors[s.get_type()] = s

# ── Find profiles ────────────────────────────────────────────────────
def find_profile(sensor, fmt=None, w=None, h=None):
    profiles = sensor.get_stream_profile_list()
    for i in range(profiles.get_count()):
        p = profiles.get_stream_profile_by_index(i).as_video_stream_profile()
        if fmt and p.get_format() != fmt:
            continue
        if w and p.get_width() != w:
            continue
        if h and p.get_height() != h:
            continue
        return profiles.get_stream_profile_by_index(i)
    return profiles.get_stream_profile_by_index(0)

# ── Shared frame storage ─────────────────────────────────────────────
lock = threading.Lock()
latest = {"ir": None, "color": None, "depth": None, "accel": None, "gyro": None}
stop_event = threading.Event()

# ── Color pipeline (separate) ────────────────────────────────────────
color_profile = find_profile(sensors[OBSensorType.COLOR_SENSOR], OBFormat.MJPG, 1280, 720)
p = color_profile.as_video_stream_profile()
print(f"Color: {p.get_format()} {p.get_width()}x{p.get_height()} @{p.get_fps()}fps")

color_pipeline = Pipeline(dev)
color_config = Config()
color_config.enable_stream(color_profile)

# ── IR pipeline (separate) ───────────────────────────────────────────
ir_profile = find_profile(sensors[OBSensorType.IR_SENSOR], OBFormat.Y8, 1280, 800)
p = ir_profile.as_video_stream_profile()
print(f"IR:    {p.get_format()} {p.get_width()}x{p.get_height()} @{p.get_fps()}fps")

# ── Depth pipeline (separate) ────────────────────────────────────────
depth_profile = find_profile(sensors[OBSensorType.DEPTH_SENSOR], OBFormat.Y14, 1280, 800)
p = depth_profile.as_video_stream_profile()
print(f"Depth: {p.get_format()} {p.get_width()}x{p.get_height()} @{p.get_fps()}fps")

# ── Start color first ────────────────────────────────────────────────
color_pipeline.start(color_config)
print("Color started")
time.sleep(0.5)

# ── IR+Depth on second pipeline ──────────────────────────────────────
depth_ir_pipeline = Pipeline(dev)
depth_ir_config = Config()
depth_ir_config.enable_stream(ir_profile)
depth_ir_config.enable_stream(depth_profile)
depth_ir_pipeline.start(depth_ir_config)
print("IR+Depth started")

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
                    af = frames.get_frame(OBFrameType.ACCEL_FRAME)
                    gf = frames.get_frame(OBFrameType.GYRO_FRAME)
                    with lock:
                        if af:
                            latest["accel"] = af.as_accel_frame().get_value()
                        if gf:
                            latest["gyro"] = gf.as_gyro_frame().get_value()
            except:
                pass
        imu_pipeline.stop()
    except Exception as e:
        print(f"IMU thread error: {e}")

imu_t = threading.Thread(target=imu_thread_fn, daemon=True)
imu_t.start()

print("All streams started. Press 'q' to quit.")
time.sleep(2)  # projector warmup

# ── Display loop ─────────────────────────────────────────────────────
frame_count = 0
fps_start = time.time()
fps_val = 0

while True:
    # Poll color
    try:
        cframes = color_pipeline.wait_for_frames(30)
        if cframes:
            cf = cframes.get_color_frame()
            if cf:
                with lock:
                    latest["color"] = cf
    except:
        pass

    # Poll IR + depth
    try:
        dframes = depth_ir_pipeline.wait_for_frames(30)
        if dframes:
            irf = dframes.get_ir_frame()
            df = dframes.get_depth_frame()
            with lock:
                if irf:
                    latest["ir"] = irf
                if df:
                    latest["depth"] = df
    except:
        pass

    frame_count += 1
    elapsed = time.time() - fps_start
    if elapsed >= 1.0:
        fps_val = frame_count / elapsed
        frame_count = 0
        fps_start = time.time()

    # ── Render ────────────────────────────────────────────────────
    with lock:
        ir_frame = latest["ir"]
        color_frame = latest["color"]
        depth_frame = latest["depth"]
        accel = latest["accel"]
        gyro = latest["gyro"]

    # Color
    color_img = np.zeros((400, 640, 3), dtype=np.uint8)
    if color_frame:
        try:
            data = np.frombuffer(color_frame.get_data(), dtype=np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if img is not None:
                color_img = cv2.resize(img, (640, 400))
        except:
            pass
    cv2.putText(color_img, "Color (MJPG)", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    # Depth
    depth_img = np.zeros((400, 640, 3), dtype=np.uint8)
    if depth_frame:
        try:
            depth16 = np.frombuffer(depth_frame.get_data(), dtype=np.uint16)
            if depth16.size >= 1280 * 800:
                depth16 = depth16[:1280 * 800].reshape((800, 1280))
                depth_norm = cv2.normalize(depth16, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                depth_img = cv2.applyColorMap(depth_norm, cv2.COLORMAP_JET)
                depth_img = cv2.resize(depth_img, (640, 400))
        except:
            pass
    cv2.putText(depth_img, "Depth (Y14 disparity)", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    # IR
    ir_img = np.zeros((400, 640, 3), dtype=np.uint8)
    if ir_frame:
        try:
            data = np.frombuffer(ir_frame.get_data(), dtype=np.uint8)
            if data.size >= 1280 * 800:
                gray = data[:1280*800].reshape((800, 1280))
                gray = cv2.resize(gray, (640, 400))
                ir_img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        except:
            pass
    cv2.putText(ir_img, "IR (Y8)", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    # IMU panel
    imu_img = np.zeros((400, 640, 3), dtype=np.uint8)
    cv2.putText(imu_img, "IMU Data", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    if accel:
        cv2.putText(imu_img, f"Accel: x={accel.x:+.3f} y={accel.y:+.3f} z={accel.z:+.3f} m/s2",
                     (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    if gyro:
        cv2.putText(imu_img, f"Gyro:  x={gyro.x:+.3f} y={gyro.y:+.3f} z={gyro.z:+.3f} dps",
                     (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    cv2.putText(imu_img, f"FPS: {fps_val:.1f}", (10, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)
    cv2.putText(imu_img, f"{info.get_name()} FW:{info.get_firmware_version()}", (10, 220),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
    cv2.putText(imu_img, f"SN: {info.get_serial_number()}", (10, 250),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
    cv2.putText(imu_img, "Press 'q' to quit", (10, 370), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 150, 255), 1)

    # 2x2 grid
    top = np.hstack([color_img, depth_img])
    bottom = np.hstack([ir_img, imu_img])
    canvas = np.vstack([top, bottom])

    cv2.imshow("CR-Scan Ferret - All Streams", canvas)
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q') or key == 27:
        break

# ── Cleanup ──────────────────────────────────────────────────────────
stop_event.set()
color_pipeline.stop()
depth_ir_pipeline.stop()
imu_t.join(timeout=2)
cv2.destroyAllWindows()
print("Done.")
