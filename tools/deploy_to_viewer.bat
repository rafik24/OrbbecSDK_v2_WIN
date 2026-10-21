@echo off
REM Deploy modified OrbbecSDK build to the pre-built OrbbecViewer and pyorbbecsdk
REM Run this after building the SDK in VS Code

set SDK_BUILD=D:\projects\orbbec\OrbbecSDK_v2\build\win_x64\bin
set SDK_SRC=D:\projects\orbbec\OrbbecSDK_v2\src\shared\environment
set VIEWER=D:\projects\orbbec\OrbbecViewer_v2.7.6_202602022045_20730ef_win_x64
set PYORBBEC=C:\Python313\Lib\site-packages

REM Detect build config (Release or Debug)
if exist "%SDK_BUILD%\Release\OrbbecSDK.dll" (
    set BUILD_CFG=Release
) else if exist "%SDK_BUILD%\Debug\OrbbecSDK.dll" (
    set BUILD_CFG=Debug
) else if exist "%SDK_BUILD%\OrbbecSDK.dll" (
    set BUILD_CFG=.
) else (
    echo ERROR: OrbbecSDK.dll not found. Build the SDK first.
    echo Looked in: %SDK_BUILD%\Release\ and %SDK_BUILD%\Debug\
    pause
    exit /b 1
)

echo Found build: %SDK_BUILD%\%BUILD_CFG%

REM === OrbbecViewer ===
echo.
echo --- OrbbecViewer ---

REM Backup originals (only first time)
if not exist "%VIEWER%\OrbbecSDK.dll.orig" (
    echo Backing up original OrbbecSDK.dll...
    copy "%VIEWER%\OrbbecSDK.dll" "%VIEWER%\OrbbecSDK.dll.orig"
)
if not exist "%VIEWER%\OrbbecSDKConfig.xml.orig" (
    echo Backing up original OrbbecSDKConfig.xml...
    copy "%VIEWER%\OrbbecSDKConfig.xml" "%VIEWER%\OrbbecSDKConfig.xml.orig"
)

echo Copying OrbbecSDK.dll to Viewer...
copy /Y "%SDK_BUILD%\%BUILD_CFG%\OrbbecSDK.dll" "%VIEWER%\OrbbecSDK.dll"

if exist "%SDK_BUILD%\%BUILD_CFG%\OrbbecSDK.pdb" (
    echo Copying OrbbecSDK.pdb to Viewer...
    copy /Y "%SDK_BUILD%\%BUILD_CFG%\OrbbecSDK.pdb" "%VIEWER%\OrbbecSDK.pdb"
)

echo Copying OrbbecSDKConfig.xml to Viewer...
copy /Y "%SDK_SRC%\OrbbecSDKConfig.xml" "%VIEWER%\OrbbecSDKConfig.xml"

REM === pyorbbecsdk ===
echo.
echo --- pyorbbecsdk (Python 3.13) ---

if not exist "%PYORBBEC%\OrbbecSDK.dll.orig" (
    echo Backing up original pyorbbecsdk OrbbecSDK.dll...
    copy "%PYORBBEC%\OrbbecSDK.dll" "%PYORBBEC%\OrbbecSDK.dll.orig"
)
if not exist "%PYORBBEC%\OrbbecSDKConfig.xml.orig" (
    echo Backing up original pyorbbecsdk OrbbecSDKConfig.xml...
    copy "%PYORBBEC%\OrbbecSDKConfig.xml" "%PYORBBEC%\OrbbecSDKConfig.xml.orig"
)

echo Copying OrbbecSDK.dll to pyorbbecsdk...
copy /Y "%SDK_BUILD%\%BUILD_CFG%\OrbbecSDK.dll" "%PYORBBEC%\OrbbecSDK.dll"

echo Copying OrbbecSDKConfig.xml to pyorbbecsdk...
copy /Y "%SDK_SRC%\OrbbecSDKConfig.xml" "%PYORBBEC%\OrbbecSDKConfig.xml"

REM === Patch ob_frame_processor.dll ===
echo.
echo --- Patching ob_frame_processor.dll for Ferret PID ---
C:\Python313\python.exe D:\projects\orbbec\patch_frameprocessor.py --all

echo.
echo Done. Run:
echo   Viewer:  %VIEWER%\OrbbecViewer.exe
echo   Python:  C:\Python313\python.exe -c "from pyorbbecsdk import *; print('OK')"
echo.
pause
