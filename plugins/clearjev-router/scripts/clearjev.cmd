@echo off
REM clearjev — thin CLI for the ClearJev router (Windows).
REM Installed to %USERPROFILE%\.local\bin by install.ps1. Usage:
REM   clearjev on | off | status | check | key | models | run
if "%~1"=="" goto help
if "%~1"=="--help" goto help
if "%~1"=="-h" goto help
set "ROUTER=%~dp0jev_route.py"
if not exist "%ROUTER%" (
  if defined CODEX_HOME (
    set "ROUTER=%CODEX_HOME%\clearjev-runtime\scripts\jev_route.py"
  ) else (
    set "ROUTER=%USERPROFILE%\.codex\clearjev-runtime\scripts\jev_route.py"
  )
)
if not exist "%ROUTER%" echo ClearJev runtime not found; reinstall ClearJev. & exit /b 1
where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 "%ROUTER%" %*
) else (
  python "%ROUTER%" %*
)
exit /b %ERRORLEVEL%
:help
echo Usage: clearjev on ^| off ^| status ^| check ^| key ^| models ^| run
echo   on/off   resume or pause pre-prompt routing (persistent, no restart needed)
echo   status   show on/off state, API key presence, routing smoke test
echo   check    full setup verification incl. live Jev ping (needs TYPESAFE_API_KEY)
echo   key      set, remove, or inspect the TypeSafe API key
echo   models   list/add/remove models and reasoning levels
echo   run      route a prompt, then start Codex with that model
echo Env: CLEARJEV_ENABLED=0 pauses for one process; prefix a prompt with 'noroute:' to skip once.
exit /b 0
