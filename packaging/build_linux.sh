#!/usr/bin/env bash
# Baut eine eigenständige Linux-App und packt sie als .tar.gz.
# MUSS auf Linux laufen (am besten auf einer möglichst alten Distribution,
# damit die glibc kompatibel bleibt).  Voraussetzung: python3 + python3-tk.
#
#   ./packaging/build_linux.sh
#
set -e
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"

echo "==> virtuelle Umgebung + Abhängigkeiten"
"$PYTHON" -m venv .build-venv
source .build-venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt pyinstaller

echo "==> App bauen"
rm -rf build dist
pyinstaller pap_editor.spec

echo "==> tar.gz erzeugen"
VERSION="1.0.0"
OUT="dist/PAP-Editor-${VERSION}-linux-x86_64.tar.gz"
# Startskript beilegen
cat > dist/PAP-Editor/starten.sh <<'EOF'
#!/usr/bin/env bash
cd "$(dirname "$0")"
exec ./PAP-Editor "$@"
EOF
chmod +x dist/PAP-Editor/starten.sh
tar -czf "$OUT" -C dist PAP-Editor

deactivate
echo "==> Fertig:  $OUT"
echo "    Entpacken und  ./PAP-Editor/starten.sh  ausführen."
