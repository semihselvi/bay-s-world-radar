@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py"
) else (
  set "PY=python"
)

echo Starting BAY-S Facebook Targeted Demand Search...
%PY% facebook_demand_search.py
set "EXITCODE=%errorlevel%"

echo.
if not "%EXITCODE%"=="0" echo Facebook Demand Search exited with code %EXITCODE%.
pause
exit /b %EXITCODE%
