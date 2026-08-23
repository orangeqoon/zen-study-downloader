@echo off
title ZEN Study Downloader Server
chcp 65001 > nul
echo ===================================================
echo   ZEN Study Downloader サーバーを起動しています...
echo ===================================================
echo.
python "%~dp0zen_download_server.py"
pause
