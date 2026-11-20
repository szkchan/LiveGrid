@echo off
cd /d "%~dp0"

rem tools\rubberband があれば exe に同梱する (テンポ補正機能用。Rubber Band は GPL)
set RB_OPT=
if exist tools\rubberband\rubberband-r3.exe set RB_OPT=--add-data "tools\rubberband;rubberband"

.venv\Scripts\python.exe -m PyInstaller main.py ^
  --name TempoExtractorAI ^
  --windowed ^
  --onedir ^
  --noconfirm ^
  --collect-all madmom ^
  --collect-all imageio_ffmpeg ^
  --collect-all matplotlib ^
  --collect-all mido ^
  %RB_OPT%
