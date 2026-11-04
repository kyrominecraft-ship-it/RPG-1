@echo off
setlocal
cd /d "%~dp0"
py -3 -m rpg --open-browser
if errorlevel 1 (
  echo.
  echo The application stopped with an error. Read the message above.
  echo Check that Python is installed and port 8000 is not already in use.
)
pause
