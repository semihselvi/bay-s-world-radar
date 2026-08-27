@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py"
) else (
  set "PY=python"
)

echo Starting BAY-S Facebook Radar V2...
%PY% facebook_radar_v2.py
set "EXITCODE=%errorlevel%"

echo.
if not "%EXITCODE%"=="0" echo Facebook Radar exited with code %EXITCODE%.
pause
exit /b %EXITCODE%
