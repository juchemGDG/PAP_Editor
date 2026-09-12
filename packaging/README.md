# PAP Editor – Pakete bauen

Der PAP Editor ist eine **Desktop-App** (Python + Tkinter). Mit
[PyInstaller](https://pyinstaller.org) wird daraus pro Betriebssystem eine
eigenständige App, die **ohne installiertes Python** startet.

> **Wichtig:** PyInstaller kann *nicht* über Plattformen hinweg bauen.
> Die macOS-App muss auf einem **Mac** gebaut werden, die Windows-App auf
> **Windows**, die Linux-App auf **Linux**.

## Ohne eigenen Rechner pro Plattform: GitHub Actions

Der Workflow `.github/workflows/build-packages.yml` baut alle drei Pakete auf
GitHubs Runnern – damit bekommt man die Windows-`.exe` auch ohne Windows-PC:

1. auf GitHub → Reiter **Actions** → **„Pakete bauen"** → **Run workflow**
   (oder einen Tag `v1.0.0` pushen)
2. nach ein paar Minuten unten am Workflow-Lauf die Artefakte herunterladen:
   `PAP-Editor-Windows` (Setup.exe + zip), `PAP-Editor-macOS` (.dmg),
   `PAP-Editor-Linux` (.tar.gz)
3. die Dateien nach `web/static/downloads/` kopieren (Namen siehe unten)

Alle Skripte bauen in `build/<plattform>/` und legen **nur** das fertige Paket
in `dist/` ab – vorhandene Pakete anderer Plattformen bleiben dort liegen.

## macOS → `.dmg`
```bash
./packaging/build_macos.sh
# Ergebnis: dist/PAP-Editor.dmg   (enthält PAP-Editor.app)
```
Hübscheres DMG-Layout optional mit `brew install create-dmg`.
Zum Verteilen ohne Warnung: App signieren & notarisieren
(Apple Developer ID nötig) – sonst muss der Nutzer beim ersten Start
Rechtsklick → „Öffnen" wählen.

## Windows → Installer `.exe`
```bat
packaging\build_windows.bat
:: Ergebnis: dist\PAP-Editor-Setup.exe   (Installer)
:: ohne Inno Setup: build\windows\dist\PAP-Editor\PAP-Editor.exe (Ordner zippen)
```
Installer-Erzeugung braucht [Inno Setup](https://jrsoftware.org/isdl.php).
Ohne Windows-Rechner: den GitHub-Actions-Workflow oben nutzen.

## Linux → `.tar.gz`
```bash
./packaging/build_linux.sh
# Ergebnis: dist/PAP-Editor-1.0.0-linux-x86_64.tar.gz
# Nutzer: entpacken, dann ./PAP-Editor/starten.sh
```
Vorher `python3-tk` installieren (z. B. `sudo apt install python3-tk`) und ein
Python mit *shared library* verwenden (`PYTHON=/usr/bin/python3 ...`; das
Codespaces-Python ist statisch gebaut und funktioniert mit PyInstaller nicht).
Auf einer möglichst **alten** Distribution bauen → beste glibc-Kompatibilität:
ein auf Ubuntu 24.04 gebautes Paket braucht glibc ≥ 2.39, der CI-Job nutzt
deshalb Ubuntu 22.04 (glibc 2.35).

## Icon (optional)
- macOS/Linux: `PAP_ICON=packaging/icon.icns ./packaging/build_macos.sh`
- Windows: `SetupIconFile`/`icon` in `pap_editor.iss` bzw. `pap_editor.spec` setzen.

## Auf der Homepage anbieten
Die drei erzeugten Dateien in den Ordner **`web/static/downloads/`** kopieren –
der Menüpunkt „Desktop-Version" in der Web-App verlinkt genau dorthin:

```bash
cp dist/PAP-Editor.dmg                          web/static/downloads/
cp dist/PAP-Editor-Setup.exe                    web/static/downloads/
cp dist/PAP-Editor-1.0.0-linux-x86_64.tar.gz    web/static/downloads/PAP-Editor-linux-x86_64.tar.gz
```

Die Dateinamen müssen zur Liste `DOWNLOADS` in `web/static/pap.js` passen
(siehe `web/static/downloads/README.md`). Fehlende Pakete erscheinen im Dialog
ausgegraut. Das Programm selbst läuft *nicht* im Browser – die Web-Version ist
ein eigenständiger Editor, die Pakete sind die Desktop-App.
