@echo off
REM clearjev — thin CLI for the ClearJev router (Windows).
REM Installed to %USERPROFILE%\.local\bin by install.ps1. Usage:
REM   clearjev on | off | status | check
if "%~1"=="" goto help
if "%~1"=="--help" goto help
if "%~1"=="-h" goto help
where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 "%~dp0jev_route.py" %*
) else (
  python "%~dp0jev_route.py" %*
)
exit /b %ERRORLEVEL%
:help
echo Usage: clearjev on ^| off ^| status ^| check
echo   on/off   resume or pause pre-prompt routing (persistent, no restart needed)
echo   status   show on/off state, API key presence, routing smoke test
echo   check    full setup verification incl. live Jev ping (needs TYPESAFE_API_KEY)
echo Env: CLEARJEV_ENABLED=0 pauses for one process; prefix a prompt with 'noroute:' to skip once.
exit /b 0
