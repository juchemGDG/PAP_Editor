# Ablageort für die Installationspakete der Desktop-Version

**Seit der GitHub-Anbindung ist dieser Ordner nur noch die Rückfallebene.**
Der Menüpunkt „Desktop-Version" in der Web-App fragt über das Flask-Backend
(`/api/downloads`) das **neueste GitHub-Release** ab und leitet den Klick direkt
auf die dort angehängte Datei weiter. Die Pakete müssen also nicht mehr von Hand
auf den Server kopiert werden – ein neues Release genügt.

Gibt es kein Release (oder ist GitHub gerade nicht erreichbar), nimmt die Web-App
eine Datei aus diesem Ordner, falls sie hier liegt. Die Namen müssen dann exakt
so lauten:

| Betriebssystem | Dateiname                          | erzeugt durch                 |
|---|---|---|
| macOS   | `PAP-Editor.dmg`                   | `./packaging/build_macos.sh`   |
| Windows | `PAP-Editor-Setup.exe`             | `packaging\build_windows.bat`  |
| Linux   | `PAP-Editor-linux-x86_64.tar.gz`   | `./packaging/build_linux.sh`   |

Dieselben Namen trägt der Workflow „Pakete bauen" an das Release an – deshalb
sind sie ohne Versionsnummer, damit die Web-App sie immer findet.

Fehlt eine Datei an beiden Stellen, bleibt der Eintrag im Dialog sichtbar, ist
aber ausgegraut („noch nicht verfügbar").

Die Pakete selbst gehören nicht ins Git-Repository (siehe `.gitignore` in
diesem Ordner).
