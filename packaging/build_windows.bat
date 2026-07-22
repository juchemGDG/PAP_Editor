@echo off
REM Baut die Windows-App (.exe) und – falls Inno Setup installiert ist –
REM einen Installer (Setup.exe).  MUSS auf Windows laufen.
REM
REM   packaging\build_windows.bat
REM
setlocal
cd /d "%~dp0.."

echo ==^> virtuelle Umgebung + Abhaengigkeiten
python -m venv .build-venv
call .build-venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller

echo ==^> App bauen
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
pyinstaller pap_editor.spec

echo ==^> Installer erzeugen (benoetigt Inno Setup: https://jrsoftware.org/isdl.php)
where iscc >nul 2>nul
if %errorlevel%==0 (
    iscc packaging\pap_editor.iss
    echo ==^> Fertig: dist\PAP-Editor-Setup.exe
) else (
    echo Inno Setup ^(iscc^) nicht gefunden – ueberspringe Installer.
    echo Die lauffaehige App liegt in  dist\PAP-Editor\PAP-Editor.exe
    echo Alternativ diesen Ordner einfach zippen und verteilen.
)

call deactivate
endlocal
