# PAP Editor

Ein kleines Tkinter-Applet zum schnellen Erstellen von Programmablaufplaenen.

## Funktionen

- Bausteine aus dem Ordner `Bilder/` per Drag and Drop auf die Flaeche ziehen
- Inhalte per Doppelklick aendern
- Pfeile per Maus zwischen Symbolen ziehen
- Speichern und Laden als JSON
- Export als PNG und JPG
- Validierung gegen ungueltige Verbindungen wie Rueckspruenge nach oben oder Zyklen

## Start

```bash
bash start_pap.sh
```

In VS Code kannst du auch direkt die Aufgabe "Start PAP Editor" ausfuehren oder die Run-Konfiguration "PAP Editor starten" mit F5 starten.

## Abhaengigkeiten

```bash
/Users/stephan/venvs/standard/bin/python -m pip install -r requirements.txt
```

Falls du den Python-Interpreter direkt starten willst, nutze den vollstaendigen Pfad mit fuehrendem Slash:

```bash
/Users/stephan/venvs/standard/bin/python pap_editor.py
```
