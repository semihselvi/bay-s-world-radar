@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py"
) else (
  set "PY=python"
)

echo Resending latest BAY-S Facebook leads with actionable links...
%PY% facebook_resend_latest.py
set "EXITCODE=%errorlevel%"

echo.
if not "%EXITCODE%"=="0" echo Resend exited with code %EXITCODE%.
pause
exit /b %EXITCODE%
