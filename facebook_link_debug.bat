@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py"
) else (
  set "PY=python"
)

echo Starting Facebook post-link diagnostic...
%PY% facebook_link_debug.py
set "EXITCODE=%errorlevel%"

echo.
if not "%EXITCODE%"=="0" echo Diagnostic exited with code %EXITCODE%.
pause
exit /b %EXITCODE%
