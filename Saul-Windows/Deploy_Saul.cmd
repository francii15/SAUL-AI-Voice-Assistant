@echo off
setlocal
cd /d "%~dp0"
call conda activate orynth
if errorlevel 1 goto failed
python "%~dp0deploy.py" %*
set "SAUL_EXIT=%ERRORLEVEL%"
pause
exit /b %SAUL_EXIT%
:failed
echo Open Anaconda Prompt and run Deploy_Saul.cmd there.
pause
exit /b 1
