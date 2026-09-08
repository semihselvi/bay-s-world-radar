@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py"
) else (
  set "PY=python"
)

echo Running OFFLINE Foreign Buyer debug - Facebook will NOT be opened...
%PY% facebook_foreign_buyer_offline_debug.py
set "EXITCODE=%errorlevel%"

echo.
if not "%EXITCODE%"=="0" echo Offline debug exited with code %EXITCODE%.
pause
exit /b %EXITCODE%
