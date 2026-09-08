@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py"
) else (
  set "PY=python"
)

echo Installing BAY-S Facebook Radar dependencies...
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo.
echo Setup complete.
echo Run facebook_discover_groups.bat to list groups or facebook_radar.bat to scan configured groups.
pause
exit /b 0

:error
echo.
echo Setup failed. Check the Python/pip error above.
pause
exit /b 1
