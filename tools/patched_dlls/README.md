# Patched DLLs for CR-Scan Ferret

The `ob_frame_processor.dll` from Orbbec's closed-source extensions has a PID
whitelist. The Gemini 215 (0x0808) and Gemini 210 (0x0809) are whitelisted but
the CR-Scan Ferret (0x069C) is not, despite being identical hardware.

## Files

- `ob_frame_processor.dll.orig` — Original unpatched DLL (from OrbbecSDK v2.7.6)
- `ob_frame_processor.dll.patched` — Patched DLL with Ferret PID (0x069C) replacing Gemini 210 (0x0809)

## What the patch does

Replaces 6 occurrences of the byte pattern `08 08 09 08` (Gemini215 + Gemini210 PIDs)
with `08 08 9C 06` (Gemini215 + Ferret PIDs) in the PID check functions.

This enables DisparityTransform, FrameUnpacker, DepthResize, and other depth
processing filters for the Ferret.

## How to apply

```
python patch_frameprocessor.py --all
```

Or manually copy `ob_frame_processor.dll.patched` to:
- `OrbbecViewer/extensions/frameprocessor/ob_frame_processor.dll`
- `C:\Python313\Lib\site-packages\extensions\frameprocessor\ob_frame_processor.dll`
