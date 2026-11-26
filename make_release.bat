@echo off
REM Builds ORTEPSauce.exe and makes the zip files for a GitHub release (see make_release.py).
cd /d "%~dp0"
call build_exe.bat nopause || goto :error
py make_release.py || goto :error
pause
exit /b 0
:error
echo Release build failed - see the messages above.
pause
exit /b 1
