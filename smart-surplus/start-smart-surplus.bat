@echo off
title Smart Surplus Launcher
echo Starting Smart Surplus...

rem Start the backend (Flask) in its own window
start "Smart Surplus - Backend" /D "%~dp0backend" cmd /k python app.py

rem Start the frontend (Vite) in its own window
start "Smart Surplus - Frontend" /D "%~dp0frontend" cmd /k npm run dev

rem Give the servers a few seconds to start, then open the site
timeout /t 6 /nobreak >nul
start "" http://localhost:5173

echo.
echo Smart Surplus is starting. Keep the two new windows open while you use the site.
echo To stop it, close those two windows.
timeout /t 5 >nul
