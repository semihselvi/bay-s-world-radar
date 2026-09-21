@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py"
) else (
  set "PY=python"
)

echo Discovering Facebook groups visible to your logged-in account...
%PY% facebook_group_scanner.py --discover
set "EXITCODE=%errorlevel%"

echo.
if not "%EXITCODE%"=="0" echo Group discovery exited with code %EXITCODE%.
pause
exit /b %EXITCODE%
