@echo off
setlocal

rem ---------------------------------------------------------------------------
rem  Launcher for website_monitor.py
rem  Keep this .bat in the SAME folder as website_monitor.py, then double-click.
rem  Uses ArcGIS Pro's Python (nothing to install). The tool window opens and
rem  this console closes itself.
rem ---------------------------------------------------------------------------

set "SCRIPT=%~dp0website_monitor.py"

set "ENV1=C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3"
set "ENV2=%LOCALAPPDATA%\Programs\ArcGIS\Pro\bin\Python\envs\arcgispro-py3"

if not exist "%SCRIPT%" (
    echo [X] Could not find website_monitor.py next to this launcher.
    echo     Both files must be in the SAME folder. Looking in:
    echo       %~dp0
    echo.
    pause
    goto :eof
)

set "PYENV="
if exist "%ENV1%\pythonw.exe" set "PYENV=%ENV1%"
if not defined PYENV if exist "%ENV2%\pythonw.exe" set "PYENV=%ENV2%"

if not defined PYENV (
    echo [X] Could not find ArcGIS Pro's Python. Searched:
    echo       %ENV1%
    echo       %ENV2%
    echo.
    pause
    goto :eof
)

rem pythonw = no console window behind the tool
start "" "%PYENV%\pythonw.exe" "%SCRIPT%"

endlocal
