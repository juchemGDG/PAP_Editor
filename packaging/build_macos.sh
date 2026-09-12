#!/bin/zsh
# Baut die macOS-App und packt sie in eine .dmg.
# MUSS auf einem Mac laufen (PyInstaller kann nicht cross-kompilieren).
#
#   ./packaging/build_macos.sh
#
set -e
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-$(command -v python3)}"
WORK="build/macos"                       # eigener Arbeitsordner – dist/ bleibt unangetastet

echo "==> virtuelle Umgebung + Abhängigkeiten"
"$PYTHON" -m venv .build-venv
source .build-venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt pyinstaller

echo "==> App bauen"
# Achtung: dist/ enthält ggf. die Pakete der anderen Plattformen und wird
# deshalb NICHT geleert. PyInstaller arbeitet in build/macos/.
rm -rf "$WORK"
mkdir -p "$WORK" dist
# optional: PAP_ICON=packaging/icon.icns  vor dem Aufruf setzen
pyinstaller pap_editor.spec --distpath "$WORK/dist" --workpath "$WORK/work" --noconfirm

echo "==> DMG erzeugen"
APP="$WORK/dist/PAP-Editor.app"
DMG="dist/PAP-Editor.dmg"
rm -f "$DMG"
# schlanke DMG nur mit Bordmitteln (hdiutil). Für ein hübscheres Layout:
#   brew install create-dmg  &&  create-dmg "$APP"
hdiutil create -volname "PAP Editor" -srcfolder "$APP" -ov -format UDZO "$DMG"

deactivate
echo "==> Fertig:  $DMG"
echo "    Für die Web-App:  cp $DMG web/static/downloads/"
