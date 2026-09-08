@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py"
) else (
  set "PY=python"
)

echo Starting BAY-S Foreign Buyer Radar V4...
%PY% facebook_foreign_buyer_radar_v4.py
set "EXITCODE=%errorlevel%"

echo.
if not "%EXITCODE%"=="0" echo Foreign Buyer Radar V4 exited with code %EXITCODE%.
pause
exit /b %EXITCODE%
