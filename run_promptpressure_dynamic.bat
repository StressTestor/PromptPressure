@echo off
setlocal enabledelayedexpansion

pushd "%~dp0"
echo.
echo ------------------------------------------
echo   PromptPressure Eval Suite – LM Studio (All in one)
echo   Working directory: %cd%
echo ------------------------------------------

rem — Gather all LM Studio configs —
set "CONFIGS="
for %%F in (config_*.yaml) do (
    findstr /ri "^[ ]*adapter:[ ]*lmstudio" "%%F" >nul 2>&1 && (
        set "CONFIGS=!CONFIGS! %%F"
    )
)

echo Running all LM Studio models together: !CONFIGS!
echo.

rem — Single invocation with aggregated Groq analysis —
python run_eval.py --multi-config !CONFIGS! --post-analyze groq

popd
endlocal
pause
