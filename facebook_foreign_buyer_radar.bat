@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py"
) else (
  set "PY=python"
)

echo Starting BAY-S Foreign Buyer Radar...
%PY% facebook_foreign_buyer_radar.py
set "EXITCODE=%errorlevel%"

echo.
if not "%EXITCODE%"=="0" echo Foreign Buyer Radar exited with code %EXITCODE%.
pause
exit /b %EXITCODE%
