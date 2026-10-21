# CR-Scan Ferret Windows Port — Progress Log

## Device Identity
- **Device:** Creality CR-Scan Ferret (OEM Orbbec Gemini 215, MX6600 ASIC)
- **USB VID/PID:** `2bc5:069c`
- **Serial:** BC2T341012J
- **Firmware:** v1.2.2
- **USB Interfaces:** 0/1=Depth, 2/3=IR, 4/5=Color, 6=IMU/HID

---

## Architecture Decision: G2 Path (preferred) vs G330/DaBaiA Path (abandoned)

### G2 Path (Gemini 215 handler — G210Device) ✓ ACTIVE
The Ferret is routed through `G210Device`, the same handler as the Gemini 215 (PID 0x0808).

**Advantages:**
- Common XU unit (4) used by default — no override needed
- No PU control crashes — G2 handler doesn't query IAMVideoProcAmp
- Calibration loads cleanly via G2AlgParamManager (depth fx=956.615, color fx=847.49)
- IMU calibration loads successfully
- All 5 sensors detected: Depth, Color, IR, Accel, Gyro
- Clean init (~130 log lines)
- Depth unit already set to 1.0mm in G210Device

**Files changed:**
1. `src/device/DevicePids.hpp` — PID constant + added to `Gemini2DevPids`
2. `src/device/gemini2/G2DeviceInfo.cpp` — route 0x069C to G210Device + name map
3. `src/shared/environment/DeviceInfoConfig.xml` — CRScanFerret in DevList
4. `src/shared/environment/OrbbecSDKConfig.xml` — CR-ScanFerret config section
5. `src/device/protocol/Protocol.cpp` — error code 2 as warning

### G330/DaBaiA Path ✗ ABANDONED
Was the Linux approach. Required 11 file changes including XU unit override, PU control guards, PresetManager/AlgParamManager try/catch wrapping. All changes still committed but inactive.

**Why abandoned:** The G2 path gives us the same results with far fewer changes. The Linux port used DaBaiA likely because V4L2 can't do multi-interface streaming and LibUVC was needed, not because of a fundamental hardware difference.

---

## Test Results (2026-03-26)

### Python (pyorbbecsdk v2.0.18, Python 3.13) — primary test tool
| Test | Result | Notes |
|------|--------|-------|
| Device enumeration | ✓ OK | "Orbbec CR-Scan Ferret, PID 0x069C, FW 1.2.2" |
| Device open | ✓ OK | All device info accessible |
| Sensor list | ✓ OK | 5 sensors: IR, Color, Depth, Accel, Gyro |
| IR profiles | ✓ OK | Y8/MJPG 1280x800 @5/10/12/13/15fps |
| Color profiles | ✗ FAIL | `"invalid vector subscript"` — stream profile filter issue |
| Depth profiles | ✗ FAIL | `"config schema is empty"` — FrameProcessor activation |
| IR streaming | ✓ OK | 15fps, Y8 1280x800, real data (mean=33.9, 97% nonzero) |
| Color streaming | ✗ FAIL | Profile listing fails first |

### OrbbecViewer
| Test | Result | Notes |
|------|--------|-------|
| Device init | ✓ OK | Full init in SDK log, calibration loaded |
| Viewer GUI | ✗ FAIL | Opens briefly then closes silently |

---

## Creality CrealityScan 4 DLL Analysis (2026-03-26)

Examined `C:\Program Files\CrealityScan 4\CrealityScan 4_Data\Plugins\x86_64\`:

**Key discoveries:**
1. **Creality uses OrbbecSDK v1** with a custom `FerretUvcDevice` class inheriting from `ScannerAbstractDevice`
2. **Stream commands go through the property system** — `VideoSensor::sendStopStreamVendorCmd` uses `setPropertyValue`, NOT direct WMF/UVC XU calls. The GM protocol is built by `HostProtocol::setPropertyValue`.
3. **Depth format is RLE** (not Y14/Y16) in Creality's config
4. **`mx6600_depth_engine.dll`** — separate depth processing from FrameProcessor
5. **`MaxStartStreamDelayMs: 5000`** for scanners (vs our 2000)
6. Also supports CR-Scan Ferret Pro, Otter Lite, and other Creality devices

**Impact on our approach:** We do NOT need to modify `WmfUvcDevicePort.cpp` for stream enable/disable. The SDK v2 `VendorPropertyAccessor` / `PropertyServer` already builds GM protocol packets. We just need to call `setPropertyValue(0x0055, 1)` etc. through the existing property system.

---

## Remaining Work (priority order)

### 1. CRITICAL: Vendor XU Stream Enable Commands
The Ferret hardware requires vendor XU commands before frames flow. Without these, UVC streaming starts at USB level but the device emits no data.

**Before depth/IR streaming:**
```
Set property 0x0055 = 1  (reset stream state)
Set property 0x000E = 1  (enable depth processing)
Set property 0x0051 = 1  (enable IR/color)
```

**On stream stop:**
```
Set property 0x004D = 1  (stop stream)
Set property 0x0003 = 0  (laser off)
```

**UPDATE (2026-03-26):** IR streaming works at 15fps WITHOUT any vendor XU commands on the G2 path! The G210Device handler starts streams correctly through standard UVC. Vendor XU commands may still be needed for depth (projector activation) but IR works out of the box.

### 2. Color Stream Profile Filter
`G2StreamProfileFilter` rejects Ferret color formats with `"invalid vector subscript"`. Needs investigation — may need Ferret-specific profile filtering.

### 3. Depth FrameProcessor Activation
`ob_frame_processor.dll` (closed-source) reports "not activated" / "config schema is empty". Options:
- Find activation key mechanism
- Skip FrameProcessor for Ferret and process raw Y14/RLE disparity data
- Use the `mx6600_depth_engine.dll` from Creality (228KB, ships with CrealityScan)

### 4. Viewer Stability
Viewer crashes after device init. Lower priority — Python works for testing.

---

## Build & Deploy

### CMake Configure
```
"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe" -DOpenCV_DIR:STRING=C:/Users/Raf/Downloads/OpenCV/opencv/build -DCMAKE_EXPORT_COMPILE_COMMANDS:BOOL=TRUE --no-warn-unused-cli -S D:/projects/orbbec/OrbbecSDK_v2 -B d:/projects/orbbec/OrbbecSDK_v2/build
```

### CMake Build (always Debug!)
```
"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe" --build d:/projects/orbbec/OrbbecSDK_v2/build --config Debug --target ALL_BUILD -j 8
```

### Deploy
Run `D:\projects\orbbec\deploy_to_viewer.bat` — copies DLL + config to both OrbbecViewer and pyorbbecsdk.

### Python Test Scripts
```
C:\Python313\python.exe D:\projects\orbbec\test_ferret.py        # enumerate + device info
C:\Python313\python.exe D:\projects\orbbec\test_ferret_ir.py     # list profiles + try IR stream
C:\Python313\python.exe D:\projects\orbbec\test_ferret_stream.py # try color stream
```

---

## Repository
- **Upstream:** https://github.com/Orbbec/OrbbecSDK_v2.git
- **Windows fork:** https://github.com/rafik24/OrbbecSDK_v2_WIN.git
- **Branch:** `cr-scan-ferret-win`
- **Handoff doc:** `CLAUDE_WINDOWS_FERRET.md`

---

## Calibration Reference (verified on Windows G2 path)
```
Camera params (1280x800):
  Depth: fx=956.615 fy=956.615 cx=638.937 cy=407.104
  RGB:   fx=847.49  fy=847.333 cx=632.655 cy=405.222

Camera params (800x600):
  Depth: fx=956.615 fy=956.615 cx=638.937 cy=307.104
  RGB:   fx=847.49  fy=847.333 cx=632.655 cy=305.222

IMU calibration: loaded successfully
```
