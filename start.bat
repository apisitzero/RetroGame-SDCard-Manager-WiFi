@echo off
chcp 65001 > nul
title ArkOS WiFi Manager
echo ============================================================
echo   ArkOS WiFi ROM & Cover Manager
echo   กำลังตรวจสอบและเริ่มต้นระบบ...
echo ============================================================
echo.

cd /d "%~dp0"

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] ไม่พบ Python ในระบบ กรุณาติดตั้ง Python 3 ก่อนใช้งาน
    pause
    exit /b
)

echo กำลังตรวจสอบแพ็กเกจที่จำเป็น...
python -m pip install -q -r requirements.txt

echo.
echo กำลังเปิดโปรแกรมและหน้าต่างเบราว์เซอร์...
python run.py

pause
