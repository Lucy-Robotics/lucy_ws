@echo off
REM Point rustup/cargo at the active Pixi env (Windows).
REM Called from Pixi [target.win.activation] scripts.

if "%CONDA_PREFIX%"=="" goto :eof

set "CARGO_HOME=%CONDA_PREFIX%\cargo"
set "RUSTUP_HOME=%CONDA_PREFIX%\rustup"
set "PATH=%CARGO_HOME%\bin;%PATH%"
