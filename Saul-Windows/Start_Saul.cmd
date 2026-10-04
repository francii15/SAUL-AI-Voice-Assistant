@echo off
setlocal
cd /d "%~dp0"
if not exist "python-path.txt" goto conda
set /p SAUL_PYTHON=<"python-path.txt"
if exist "%SAUL_PYTHON%" goto launch
:conda
call conda activate orynth
if errorlevel 1 goto failed
set "SAUL_PYTHON=python"
:launch
"%SAUL_PYTHON%" "%~dp0run_saul.py" --semantic-commands --further-reading %*
set "SAUL_EXIT=%ERRORLEVEL%"
if not "%SAUL_EXIT%"=="0" pause
exit /b %SAUL_EXIT%
:failed
echo Open Anaconda Prompt, activate orynth, and run this script again.
pause
exit /b 1
