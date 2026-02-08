@echo off
REM ============================================================
REM  BITS Whisperer — Build Executable
REM
REM  Usage:
REM    build.bat                          Standard build (folder output)
REM    build.bat --lean                   Clean venv build (smallest output)
REM    build.bat --onefile                Single-file .exe (slower startup)
REM    build.bat --clean                  Remove previous build artefacts
REM    build.bat --name "My App"          Custom executable name
REM
REM  Flags can be combined:
REM    build.bat --lean --clean
REM    build.bat --onefile --name bw
REM ============================================================

setlocal

REM -- Ensure we run from the project root --
cd /d "%~dp0"

REM -- Check Python is available --
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not found on PATH.
    echo        Please install Python 3.10+ and add it to PATH.
    exit /b 1
)

echo.
echo ============================================================
echo   BITS Whisperer — Build
echo ============================================================
echo.

python build_installer.py %*

if %errorlevel% neq 0 (
    echo.
    echo Build failed with exit code %errorlevel%.
    exit /b %errorlevel%
)

echo.
echo Done.
exit /b 0
