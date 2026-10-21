# Unlocking the Creality CR-Scan Ferret on Windows — Open SDK Support

**TL;DR:** We reverse-engineered the Creality CR-Scan Ferret 3D scanner to work with the open-source Orbbec SDK v2 on Windows, freeing it from Creality's proprietary software. All streams work: depth, color, IR, and IMU. It now works with OrbbecViewer, Python, and any Orbbec-compatible application — including RTAB-Map, Open3D, and ROS2.

## The Problem

The CR-Scan Ferret (USB `2bc5:069c`) is actually an **Orbbec Gemini 215** depth camera rebranded by Creality. Orbbec makes the hardware; Creality locks it to their scanning app. The Ferret's USB PID isn't in Orbbec's SDK whitelist, so open-source software can't see it.

## What We Did

1. **Identified the hardware** — The Ferret uses the same MX6600 ASIC, sensors (dual OV9282 IR, OV9782 RGB), and firmware protocol as the Gemini 215. FCC filing `2A2CLWBF1` confirmed Orbbec as the manufacturer.

2. **Added the PID to OrbbecSDK v2** — Registered `0x069C` in the Gemini 2 device family and created a dedicated `FerretDevice` handler that routes through the same code path as the Gemini 215.

3. **Sent vendor commands for depth** — The structured light projector needs firmware activation via vendor XU properties (`0x0055`, `0x000E`, `0x0051`) before depth data flows. We send these through the SDK's existing property system.

4. **Patched the closed-source depth filter DLL** — Orbbec's `ob_frame_processor.dll` has a PID whitelist. We binary-patched 6 bytes (replacing the Gemini 210 PID with the Ferret PID) to enable the DisparityTransform that converts raw disparity to calibrated depth.

## What Works

| Stream | Format | Resolution | FPS | Status |
|--------|--------|-----------|-----|--------|
| Depth | Y16 (calibrated mm) | 1280x800 | 30 | Working |
| Color | MJPG | 1280x720 / 1920x1080 | 30 | Working |
| IR | Y8 | 1280x800 | 30 | Working |
| Accel | 6-axis | — | 200Hz | Working |
| Gyro | 6-axis | — | 200Hz | Working |
| Point Cloud | Depth + Color | 1280x800 | 30 | Working |

## What This Enables

Any software using Orbbec SDK v2 now works with the Ferret:

- **RTAB-Map** — SLAM with depth + color + IMU
- **Open3D** — Python point cloud processing via pyorbbecsdk
- **ROS2** — via the `orbbec_camera` package
- **OrbbecViewer** — full GUI with all streams and point cloud
- **Custom Python** — `pip install pyorbbecsdk2` + our patched SDK DLL

## How to Use It

```bash
git clone https://github.com/rafik24/OrbbecSDK_v2_WIN.git
cd OrbbecSDK_v2_WIN
git checkout cr-scan-ferret-win
# Build, deploy, and patch — see PROGRESS.md for details
python tools/patch_frameprocessor.py --all
```

## The Code

~600 lines of new C++ code (one file: `FerretDevice.cpp`), plus PID registrations in 5 existing files. Zero changes to the USB transport layer. The DLL patch is 6 bytes.

**Repository:** [github.com/rafik24/OrbbecSDK_v2_WIN](https://github.com/rafik24/OrbbecSDK_v2_WIN) (branch: `cr-scan-ferret-win`)

## Credits

Built by Raf with Claude Code. Based on prior Linux work that proved the concept. The Ferret community deserves open tools.
