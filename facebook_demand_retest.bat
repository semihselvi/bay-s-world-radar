@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py"
) else (
  set "PY=python"
)

echo Starting BAY-S Facebook Demand RETEST with live link capture...
set "FACEBOOK_DEMAND_RETEST=1"
%PY% facebook_demand_runner.py
set "EXITCODE=%errorlevel%"

echo.
if not "%EXITCODE%"=="0" echo Facebook Demand Retest exited with code %EXITCODE%.
pause
exit /b %EXITCODE%
