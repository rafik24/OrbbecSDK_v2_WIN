# CR-Scan Ferret — Open-Source Windows Driver via OrbbecSDK v2

## Overview

This document describes how we reverse-engineered the Creality CR-Scan Ferret 3D scanner to work with the open-source Orbbec SDK v2 on Windows. The result is full support for all sensor streams (depth, color, IR, IMU) in any Orbbec-compatible application, freeing the Ferret from Creality's proprietary CrealityScan software.

**Repository:** [github.com/rafik24/OrbbecSDK_v2_WIN](https://github.com/rafik24/OrbbecSDK_v2_WIN)
**Branch:** `cr-scan-ferret-win`

---

## 1. Device Identification

The Creality CR-Scan Ferret is not a Creality-designed product. It is an **Orbbec Gemini 215** depth camera, manufactured by Orbbec and branded by Creality for the consumer 3D scanning market.

| Property | Value |
|----------|-------|
| USB VID/PID | `2bc5:069c` |
| ASIC | Orbbec MX6600 |
| IR sensors | Dual OmniVision OV9282 (stereo, 1280x800) |
| RGB sensor | OV9782 (1920x1080) |
| Laser | AW36514 structured light projector |
| IMU | InvenSense ICM-40608 (6-axis, 200Hz) |
| Firmware | v1.2.2 |
| USB interfaces | 0/1=Depth, 2/3=IR, 4/5=Color, 6=IMU/HID |
| Equivalent device | Orbbec Gemini 215 (PID `0x0808`) |

Evidence: FCC filing `2A2CLWBF1`, identical USB descriptor layout, same MX6600 register set, matching calibration parameter structure.

---

## 2. Why It Doesn't Work Out of the Box

The Orbbec SDK v2 supports the Gemini 215 (PID `0x0808`) but not the Ferret (PID `0x069C`). Three barriers:

1. **PID not in whitelist** — The SDK's device enumeration ignores unknown PIDs
2. **Closed-source depth filter DLL** — `ob_frame_processor.dll` has an internal PID whitelist that gates depth processing filters (DisparityTransform, FrameUnpacker)
3. **Vendor stream enable commands** — The structured light projector requires firmware activation via vendor XU properties before depth data flows

---

## 3. Architecture Decision: G2 Path

The Ferret was initially tested on the G330/DaBaiA device handler path (used in the Linux port). This required extensive modifications: XU unit overrides, PU control guards, PresetManager/AlgParamManager try-catch wrapping.

We discovered that routing through the **G2/G210Device path** (same as the Gemini 215) works far better:

- Correct XU unit (4, common Orbbec) used by default
- No PU control crashes
- Calibration loads cleanly via G2AlgParamManager
- All 5 sensors detected with correct profiles
- Much cleaner initialization (~130 log lines vs ~1450)

The final implementation uses a **dedicated `FerretDevice` class** that inherits from `DeviceBase` with G2 protocol, adapted for Ferret-specific quirks.

---

## 4. Implementation Details

### 4.1 SDK Changes (~600 lines new code)

#### FerretDevice.cpp (new file, 525 lines)
The core of the implementation. A dedicated device handler that:
- Uses G2 protocol (common XU unit 4, G2AlgParamManager, G2StreamProfileFilter)
- Wraps all component creation in `TRY_EXECUTE` for resilience
- Does not attach FrameProcessor to sensors (graceful fallback if private filter library rejects the PID)
- Sends vendor XU stream enable commands (`0x0055=1`, `0x000E=1`, `0x0051=1`) before depth streaming via the SDK's property system
- Sends stream stop commands (`0x004D=1`, `0x0003=0`) on shutdown
- Pre-binds disparity parameters during depth sensor creation
- Removes non-depth formats (NV12, BGR, BGRA, Y8, Y10) from the depth sensor profile list
- Sets mirror defaults for IR, depth, and color to match sensor orientation
- Skips G2StreamProfileFilter for depth sensor (firmware's effective profile list doesn't include depth formats)

#### PID Registration (5 files modified)
- `DevicePids.hpp` — `OB_DEVICE_CR_SCAN_FERRET_PID = 0x069C` + added to `Gemini2DevPids`
- `G2DeviceInfo.cpp` — Route `0x069C` to `FerretDevice`, added to device name map
- `DeviceInfoConfig.xml` — CRScanFerret entry in DevList
- `OrbbecSDKConfig.xml` — CR-ScanFerret config section (heartbeat off, timestamp fitter off, 30fps defaults)
- `DeviceClockSynchronizer.cpp` — Ferret PID in Mx6600DevPids

#### Protocol.cpp (1 file modified)
- Treat firmware error code 2 (unsupported request) as warning instead of throwing

#### G2StreamProfileFilter.cpp (1 file modified)
- Try-catch around `fetchEffectiveStreamProfiles()`
- Return all profiles unfiltered when effective profiles are empty
- Fixed `continue` → `break` in inner matching loop (was adding duplicate profiles)

### 4.2 DLL Binary Patch (ob_frame_processor.dll)

The closed-source `ob_frame_processor.dll` contains a PID whitelist. We identified 6 locations where the Gemini 215 PID (`0x0808`) and Gemini 210 PID (`0x0809`) are stored as a 4-byte pattern in PID check functions:

```
Original: 08 08 09 08  (Gemini 215 + Gemini 210)
Patched:  08 08 9C 06  (Gemini 215 + CR-Scan Ferret)
```

This enables: DisparityTransform, FrameUnpacker, DepthResize, HardwareD2DCorrectionFilter, and other depth processing filters.

The patch script (`tools/patch_frameprocessor.py`) automates this:
```bash
python tools/patch_frameprocessor.py --all
```

### 4.3 Vendor XU Stream Enable Protocol

The Ferret's structured light projector requires firmware activation before depth data flows. These commands are sent via the SDK's property system (GM protocol, 64-byte XU packets):

**Before depth streaming:**
```
Property 0x0055 = 1  (reset stream state)
Property 0x000E = 1  (enable depth processing)
Property 0x0051 = 1  (enable IR/projector)
```

**On stream stop:**
```
Property 0x004D = 1  (stop stream)
Property 0x0003 = 0  (laser off)
```

These are sent through the existing `PropertyServer::setPropertyValueT()` mechanism — no USB transport layer modifications needed.

---

## 5. Reverse Engineering Methodology

### 5.1 Creality DLL Analysis
We examined `CrealityScan 4.1.7` (`C:\Program Files\CrealityScan 4\CrealityScan 4_Data\Plugins\x86_64\`):

- **OrbbecSDK.dll** (8.8MB) — Custom OrbbecSDK v1 build with `FerretUvcDevice` class in `src\core\device\3DScanner\FerretDevice.cpp`
- **mx6600_depth_engine.dll** (228KB) — MX6600 ASIC register configuration tool (not a runtime depth processor)
- **lib_orbbec_scan.dll** (67MB) — Scanning pipeline with Ferret-specific stream handling

Key findings from string analysis:
- Stream commands go through `VideoSensor::sendStopStreamVendorCmd` using `setPropertyValue`, not direct UVC XU calls
- Creality uses RLE format for depth (we use Y14→Y16 via DisparityTransform)
- `MaxStartStreamDelayMs: 5000` for scanners
- FerretUvcDevice inherits from `ScannerAbstractDevice`, not `Gemini2Device`

### 5.2 PID Whitelist Discovery
Binary analysis of `ob_frame_processor.dll` revealed:
- Gemini 215 (0x0808): 7 occurrences as uint16 LE
- Gemini 210 (0x0809): 6 occurrences
- Ferret (0x069C): 0 occurrences

The 6 paired occurrences of `0808 0908` are in identical function prologues — PID check functions for different filter types. Patching these to `0808 9C06` unlocks all depth processing.

### 5.3 Linux Port Reference
Prior work on Linux (branch `cr-scan-ferret-clean`) proved the concept with 11 file changes on the DaBaiA/G330 path. The dedicated `FerretDevice` approach (branch `cr-scan-ferret-device`) was ported to Windows with the G2 path adaptation.

---

## 6. Results

### Streaming Performance
| Stream | Format | Resolution | FPS | Data Quality |
|--------|--------|-----------|-----|-------------|
| Depth | Y16 (calibrated mm) | 1280x800 | 30 | Valid depth after 5-8s projector warmup |
| Color | MJPG | 1280x720 | 30 | Full quality |
| Color | MJPG | 1920x1080 | 30 | Full quality |
| IR | Y8 | 1280x800 | 30 | Structured light pattern visible |
| Accel | 6-axis | — | 200Hz | Calibrated, gravity vector correct |
| Gyro | 6-axis | — | 200Hz | Calibrated |
| Point Cloud | Depth + Color | 1280x800 | 30 | Working in OrbbecViewer |

### Calibration Data (loaded from device)
```
Camera params (1280x800):
  Depth: fx=956.615 fy=956.615 cx=638.937 cy=407.104
  RGB:   fx=847.49  fy=847.333 cx=632.655 cy=405.222

IMU calibration: loaded successfully
Baseline: 19.536mm (from transform matrix)
```

---

## 7. Compatible Applications

Any software using Orbbec SDK v2 now works with the Ferret:

### RTAB-Map
Real-time SLAM with depth + color + IMU. Install the `orbbec_camera` ROS2 package, point it at the Ferret, and launch RTAB-Map.

### Open3D (Python)
```python
from pyorbbecsdk import *
import open3d as o3d

pipeline = Pipeline()
config = Config()
config.enable_stream(StreamProfile(OBSensorType.DEPTH_SENSOR))
config.enable_stream(StreamProfile(OBSensorType.COLOR_SENSOR))
pipeline.start(config)

frames = pipeline.wait_for_frames(1000)
depth = frames.get_depth_frame()
color = frames.get_color_frame()
# Convert to Open3D point cloud, run TSDF fusion, export PLY
```

### OrbbecViewer
Full GUI with 2D stream preview, point cloud visualization, device controls, and recording. Just replace `OrbbecSDK.dll` and patch the frame processor DLL.

### ROS2
The `orbbec_camera` ROS2 package supports all Orbbec SDK v2 devices. With our changes, the Ferret appears as a standard depth camera.

### Custom Applications
Build against OrbbecSDK v2 with our modifications. The C API (`libobsensor`) provides full access to all streams and device properties.

---

## 8. Build & Deploy

### Prerequisites
- Windows 10/11, Visual Studio 2022 Build Tools (with ATL component)
- CMake 3.15+, Python 3.13 (for pyorbbecsdk testing)

### Build
```bash
git clone https://github.com/rafik24/OrbbecSDK_v2_WIN.git
cd OrbbecSDK_v2_WIN
git checkout cr-scan-ferret-win

mkdir build && cd build
cmake -DOpenCV_DIR=C:/path/to/opencv/build ..
cmake --build . --config Debug -j 8
```

### Deploy to OrbbecViewer
```bash
copy build\win_x64\bin\OrbbecSDK.dll <OrbbecViewer_dir>\OrbbecSDK.dll
copy src\shared\environment\OrbbecSDKConfig.xml <OrbbecViewer_dir>\OrbbecSDKConfig.xml
python tools\patch_frameprocessor.py <OrbbecViewer_dir>\extensions\frameprocessor\ob_frame_processor.dll
```

### Deploy to pyorbbecsdk
```bash
pip install pyorbbecsdk2
copy build\win_x64\bin\OrbbecSDK.dll C:\Python313\Lib\site-packages\OrbbecSDK.dll
python tools\patch_frameprocessor.py --all
```

### Test
```bash
python tools\test_ferret.py          # Device enumeration
python tools\ferret_viewer.py        # All streams GUI
```

---

## 9. Known Limitations

- **D2C alignment** — Hardware depth-to-color alignment is unsupported (firmware returns cmdVersion 0xFFFF). Software alignment via the Align filter works.
- **Projector warmup** — 5-8 seconds before depth data fills in (structured light projector characteristic)
- **DLL patch required** — The closed-source `ob_frame_processor.dll` needs binary patching. This could be avoided if Orbbec adds `0x069C` to their whitelist.
- **Timestamp offset** — ~4.3s difference between color and depth timestamp domains. GlobalTimestampFitter is disabled.

---

## 10. File Summary

### New Files
| File | Lines | Purpose |
|------|-------|---------|
| `src/device/gemini2/FerretDevice.cpp` | 540 | Dedicated device handler |
| `src/device/gemini2/FerretDevice.hpp` | 40 | Header |
| `tools/patch_frameprocessor.py` | 65 | DLL PID patcher |
| `tools/ferret_viewer.py` | 200 | Python all-streams viewer |
| `tools/test_ferret*.py` | 150 | Test scripts |
| `tools/deploy_to_viewer.bat` | 75 | Deploy automation |
| `PROGRESS.md` | 150 | Development log |

### Modified Files
| File | Change |
|------|--------|
| `src/device/DevicePids.hpp` | PID constant + Gemini2DevPids entry |
| `src/device/gemini2/G2DeviceInfo.cpp` | FerretDevice routing + name map |
| `src/device/gemini2/CMakeLists.txt` | Added FerretDevice source files |
| `src/device/gemini2/G2StreamProfileFilter.cpp` | Try-catch + empty fallback + break fix |
| `src/device/protocol/Protocol.cpp` | Error code 2 as warning |
| `src/device/component/timestamp/DeviceClockSynchronizer.cpp` | Ferret PID in Mx6600DevPids |
| `src/shared/environment/DeviceInfoConfig.xml` | CRScanFerret device entry |
| `src/shared/environment/OrbbecSDKConfig.xml` | CR-ScanFerret config section |

### Binary Patches
| File | Patch | Purpose |
|------|-------|---------|
| `ob_frame_processor.dll` | 6 × `0908` → `9C06` | Enable depth filters for Ferret PID |

---

## 11. Credits

- **Raf** ([@rafik24](https://github.com/rafik24)) — Hardware research, testing, project direction
- **Claude Code** (Anthropic) — SDK development, reverse engineering, documentation
- Prior Linux work proved the Ferret = Gemini 215 equivalence and the vendor XU protocol
