@echo off
setlocal
cd /d "%~dp0"
set "SAUL_PYTHON="
set "SAUL_ENV="
set "SAUL_CONDA="
if exist "python-path.txt" set /p SAUL_PYTHON=<"python-path.txt"
if not defined SAUL_PYTHON goto findconda
if not exist "%SAUL_PYTHON%" goto findconda
for %%I in ("%SAUL_PYTHON%") do set "SAUL_ENV=%%~dpI"
if exist "%SAUL_ENV%..\..\condabin\conda.bat" set "SAUL_CONDA=%SAUL_ENV%..\..\condabin\conda.bat"
if exist "%SAUL_ENV%condabin\conda.bat" set "SAUL_CONDA=%SAUL_ENV%condabin\conda.bat"
:findconda
if defined SAUL_CONDA goto activate
if exist "%USERPROFILE%\anaconda3\condabin\conda.bat" set "SAUL_CONDA=%USERPROFILE%\anaconda3\condabin\conda.bat"
if defined SAUL_CONDA goto activate
if exist "%USERPROFILE%\miniconda3\condabin\conda.bat" set "SAUL_CONDA=%USERPROFILE%\miniconda3\condabin\conda.bat"
if defined SAUL_CONDA goto activate
for /f "delims=" %%I in ('where conda.bat 2^>nul') do set "SAUL_CONDA=%%I"
if not defined SAUL_CONDA goto failed
:activate
if defined SAUL_ENV goto activatepath
call "%SAUL_CONDA%" activate orynth
if errorlevel 1 goto failed
set "SAUL_PYTHON=%CONDA_PREFIX%\python.exe"
goto launch
:activatepath
call "%SAUL_CONDA%" activate "%SAUL_ENV%."
if errorlevel 1 goto failed
:launch
"%SAUL_PYTHON%" "%~dp0saul_desktop.py"
set "SAUL_EXIT=%ERRORLEVEL%"
if not "%SAUL_EXIT%"=="0" pause
exit /b %SAUL_EXIT%
:failed
echo Saul could not activate its Python environment.
echo Open Anaconda Prompt and run: conda activate orynth
 echo Then redeploy Saul from that environment.
pause
exit /b 1
