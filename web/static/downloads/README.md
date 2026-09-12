# Ablageort für die Installationspakete der Desktop-Version

Der Menüpunkt **„Desktop-Version"** in der Web-App verlinkt auf die Dateien in
genau diesem Ordner. Flask liefert `web/static/` unter der Adresse `/` aus, die
Pakete sind deshalb ohne weitere Konfiguration unter
`http://<server>:5000/downloads/<dateiname>` erreichbar.

Die Dateinamen müssen exakt so lauten (siehe `DOWNLOADS` in
`web/static/pap.js`):

| Betriebssystem | Dateiname                          | erzeugt durch                 |
|---|---|---|
| macOS   | `PAP-Editor.dmg`                   | `./packaging/build_macos.sh`   |
| Windows | `PAP-Editor-Setup.exe`             | `packaging\build_windows.bat`  |
| Linux   | `PAP-Editor-linux-x86_64.tar.gz`   | `./packaging/build_linux.sh`   |

Ohne Windows-Rechner liefert der GitHub-Actions-Workflow **„Pakete bauen"**
(`.github/workflows/build-packages.yml`) alle drei Pakete als Artefakte –
siehe `packaging/README.md`.

Nach dem Bauen also z. B.:

```bash
cp dist/PAP-Editor.dmg web/static/downloads/
```

Der Linux-Build heißt im `dist/`-Ordner `PAP-Editor-1.0.0-linux-x86_64.tar.gz`
und muss beim Kopieren auf den Namen aus der Tabelle umbenannt werden – oder
man passt den Namen in `DOWNLOADS` in `web/static/pap.js` an.

Fehlt eine Datei, bleibt der Eintrag im Dialog sichtbar, ist aber ausgegraut
(„noch nicht verfügbar"). Man kann also mit einer Plattform anfangen.

Die Pakete selbst gehören nicht ins Git-Repository (siehe `.gitignore` in
diesem Ordner).
