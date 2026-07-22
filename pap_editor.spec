# PyInstaller-Spezifikation für den PAP Editor
# Baut eine eigenständige GUI-App (ohne Konsolenfenster).
# Aufruf:  pyinstaller pap_editor.spec
import os

block_cipher = None

# Der Ordner "Bilder" wird mitgepackt (aktuell zeichnet das Programm zwar
# vektoriell, so ist die App aber vollständig und zukunftssicher).
datas = []
if os.path.isdir("Bilder"):
    datas.append(("Bilder", "Bilder"))

a = Analysis(
    ["pap_editor.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=["PIL._tkinter_finder"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PAP-Editor",
    debug=False,
    strip=False,
    upx=False,
    console=False,          # GUI-App, kein Terminalfenster
    icon=os.environ.get("PAP_ICON") or None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="PAP-Editor",
)

# Auf macOS zusätzlich ein .app-Bundle erzeugen
import sys
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="PAP-Editor.app",
        icon=os.environ.get("PAP_ICON") or None,
        bundle_identifier="de.gdg-stuttgart.papeditor",
        info_plist={
            "CFBundleName": "PAP Editor",
            "CFBundleDisplayName": "PAP Editor",
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
        },
    )
