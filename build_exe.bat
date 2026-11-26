@echo off
REM ---------------------------------------------------------------------------
REM  Builds "ORTEPSauce.exe" with PyInstaller.
REM  Run from the folder that contains the "ortepsauce" folder and this file.
REM  Result: dist\ORTEPSauce\ORTEPSauce.exe  (copy the whole folder)
REM ---------------------------------------------------------------------------
cd /d "%~dp0"

echo [1/3] Installing the requirements and PyInstaller ...
py -m pip install -r ortepsauce\requirements.txt pyinstaller || goto :error

echo [2/3] Drawing the program icon ...
py make_icon.py || goto :error

echo [3/3] Building the program (takes 1-3 minutes) ...
py -m PyInstaller --noconfirm --clean --windowed ^
  --name "ORTEPSauce" ^
  --icon ortepsauce.ico ^
  --collect-data customtkinter ^
  --collect-submodules OpenGL ^
  --collect-submodules pyopengltk ^
  --hidden-import PIL._tkinter_finder ^
  --add-data "ortepsauce\icon.ico;ortepsauce" ^
  --add-data "ortepsauce\icon.png;ortepsauce" ^
  --hidden-import matplotlib.backends.backend_pdf ^
  --hidden-import matplotlib.backends.backend_svg ^
  --hidden-import matplotlib.backends.backend_ps ^
  --hidden-import matplotlib.backends.backend_agg ^
  --hidden-import matplotlib.backends.backend_tkagg ^
  --exclude-module PySide6 --exclude-module PySide2 --exclude-module PyQt5 --exclude-module PyQt6 ^
  --exclude-module IPython --exclude-module pytest ^
  ortepsauce_launcher.py || goto :error

echo.
echo Done:  "%~dp0dist\ORTEPSauce\ORTEPSauce.exe"
echo Copy the whole "dist\ORTEPSauce" folder; the .exe needs the files next to it.
if /i not "%~1"=="nopause" pause
exit /b 0

:error
echo.
echo Build failed - see the messages above.
if /i not "%~1"=="nopause" pause
exit /b 1
