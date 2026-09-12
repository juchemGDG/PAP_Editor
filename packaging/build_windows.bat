@echo off
REM Baut die Windows-App (.exe) und – falls Inno Setup installiert ist –
REM einen Installer (Setup.exe).  MUSS auf Windows laufen.
REM
REM   packaging\build_windows.bat
REM
REM Ohne Windows-Rechner: den Workflow "Pakete bauen" auf GitHub starten
REM (Actions -> Pakete bauen -> Run workflow), er baut die .exe auf einem
REM Windows-Runner.
setlocal
cd /d "%~dp0.."

echo ==^> virtuelle Umgebung + Abhaengigkeiten
python -m venv .build-venv
call .build-venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller

echo ==^> App bauen
REM dist\ wird NICHT geleert – dort liegen ggf. die Pakete der anderen
REM Plattformen. PyInstaller arbeitet in build\windows\.
if exist build\windows rmdir /s /q build\windows
if not exist dist mkdir dist
pyinstaller pap_editor.spec --distpath build\windows\dist --workpath build\windows\work --noconfirm

echo ==^> Installer erzeugen (benoetigt Inno Setup: https://jrsoftware.org/isdl.php)
where iscc >nul 2>nul
if %errorlevel%==0 (
    iscc packaging\pap_editor.iss
    echo ==^> Fertig: dist\PAP-Editor-Setup.exe
    echo     Fuer die Web-App: copy dist\PAP-Editor-Setup.exe web\static\downloads\
) else (
    echo Inno Setup ^(iscc^) nicht gefunden – ueberspringe Installer.
    echo Die lauffaehige App liegt in  build\windows\dist\PAP-Editor\PAP-Editor.exe
    echo Alternativ diesen Ordner einfach zippen und verteilen.
)

call deactivate
endlocal
