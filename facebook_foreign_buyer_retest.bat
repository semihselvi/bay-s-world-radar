@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py"
) else (
  set "PY=python"
)

echo Starting BAY-S Foreign Buyer SAFE RETEST...
set "FACEBOOK_FOREIGN_BUYER_RETEST=1"
%PY% facebook_foreign_buyer_radar_v2.py
set "EXITCODE=%errorlevel%"

echo.
if not "%EXITCODE%"=="0" echo Foreign Buyer Safe Retest exited with code %EXITCODE%.
pause
exit /b %EXITCODE%
