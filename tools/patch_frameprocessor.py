"""Patch ob_frame_processor.dll to accept CR-Scan Ferret PID (0x069C).

The closed-source ob_frame_processor.dll has a PID whitelist that includes
the Gemini 215 (0x0808) and Gemini 210 (0x0809) but not the CR-Scan Ferret
(0x069C). Since the Ferret is identical hardware to the Gemini 215, we patch
the Gemini 210 PID entries to Ferret PID entries.

Pattern: 0x0808 0x0809 (two uint16 LE PIDs stored as a dword)
Replace: 0x0808 0x069C (keep Gemini 215, replace Gemini 210 with Ferret)

This enables the DisparityTransform, FrameUnpacker, and other depth
processing filters for the Ferret.

Usage:
    python patch_frameprocessor.py <path_to_ob_frame_processor.dll>
    python patch_frameprocessor.py --all  # patch all known locations
"""
import sys
import shutil
import struct
import os

KNOWN_LOCATIONS = [
    # OrbbecViewer
    r"D:\projects\orbbec\OrbbecViewer_v2.7.6_202602022045_20730ef_win_x64\extensions\frameprocessor\ob_frame_processor.dll",
    # pyorbbecsdk
    r"C:\Python313\Lib\site-packages\extensions\frameprocessor\ob_frame_processor.dll",
]

OLD_PATTERN = bytes([0x08, 0x08, 0x09, 0x08])  # Gemini215 + Gemini210
NEW_PATTERN = bytes([0x08, 0x08, 0x9C, 0x06])  # Gemini215 + Ferret

def patch_dll(path):
    if not os.path.exists(path):
        print(f"  SKIP: {path} (not found)")
        return False

    data = bytearray(open(path, 'rb').read())

    # Check if already patched
    if NEW_PATTERN in data:
        print(f"  OK:   {path} (already patched)")
        return True

    count = data.count(OLD_PATTERN)
    if count == 0:
        print(f"  SKIP: {path} (no matching pattern found)")
        return False

    # Backup
    bak = path + '.orig'
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
        print(f"  Backup: {bak}")

    # Patch
    idx = 0
    patched = 0
    while True:
        idx = data.find(OLD_PATTERN, idx)
        if idx == -1:
            break
        data[idx:idx+4] = NEW_PATTERN
        patched += 1
        idx += 4

    open(path, 'wb').write(data)
    print(f"  PATCHED: {path} ({patched} locations)")
    return True

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <path_to_dll>")
        print(f"       {sys.argv[0]} --all")
        sys.exit(1)

    if sys.argv[1] == '--all':
        print("Patching all known ob_frame_processor.dll locations...")
        for path in KNOWN_LOCATIONS:
            patch_dll(path)
    else:
        patch_dll(sys.argv[1])

if __name__ == '__main__':
    main()
