@echo off
setlocal enabledelayedexpansion

pushd "%~dp0"
echo.
echo ------------------------------------------
echo   PromptPressure Eval Suite – Cloud (OpenRouter)
echo   Working directory: %cd%
echo ------------------------------------------

echo.
echo Note: Ensure OPENROUTER_API_KEY is set in your environment or .env (run_eval.py loads .env automatically).
echo Metrics will be exposed at http://localhost:8000 while the run is active.

echo.
rem — Gather all OpenRouter configs —
set "CONFIGS="
for %%F in (config_*.yaml) do (
    findstr /ri "^[ ]*adapter:[ ]*openrouter" "%%F" >nul 2>&1 && (
        set "CONFIGS=!CONFIGS! %%F"
    )
)

if "!CONFIGS!"=="" (
  echo [ERROR] No OpenRouter configs found. Ensure files like config_openrouter_*.yaml exist.
  goto :end
)


echo Running OpenRouter models together: !CONFIGS!
echo.

rem — Single invocation with aggregated OpenRouter post-analysis —
python run_eval.py --multi-config !CONFIGS! --post-analyze openrouter
if %errorlevel% neq 0 goto :end
echo.
echo Aggregating OpenRouter pass rates...
python scripts\aggregate_openrouter_scores.py

:end
popd
endlocal
pause
