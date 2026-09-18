@echo off
cd /d "C:\Users\pir\Documents\KYB DATABASE"
call .venv\Scripts\activate.bat >nul 2>&1
python load.py run gleif > downloads\gleif_run.log 2>&1