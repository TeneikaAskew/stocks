@echo off
rem Hermetic test suite tripwire (FEAT-CICD-001): the Windows form of the
rem extensionless script beside it, which Python cannot run on Windows.
echo hermetic test suite: real %~n0 refused: %* 1>&2
exit /b 97
