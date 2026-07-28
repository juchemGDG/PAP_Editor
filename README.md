# PAP Editor

Ein kleines Tkinter-Applet zum schnellen Erstellen von Programmablaufplaenen.

## Funktionen

- Bausteine aus dem Ordner `Bilder/` per Drag and Drop auf die Flaeche ziehen
- Inhalte per Doppelklick aendern
- Pfeile per Maus zwischen Symbolen ziehen
- Speichern und Laden als JSON
- Export als PNG und JPG
- Validierung gegen ungueltige Verbindungen wie Rueckspruenge nach oben oder Zyklen
- Ausfuehrliche Plausibilitaetspruefung nach einem festen Regelkatalog (Button "Pruefen")

## Plausibilitaetspruefung

Der Button "Pruefen" fuehrt ein Regelwerk aus, das sich an den Konventionen fuer
Programmablaufplaene (DIN 66001) orientiert. Jede Regel hat eine ID (z. B.
`R10`), einen Schweregrad (Fehler/Hinweis) und erzeugt eine kurze, an die
Schuelerin/den Schueler gerichtete Meldung. Die betroffenen Bloecke/Pfeile
werden nach der Pruefung automatisch markiert. Funktionen (Unterablaufplaene)
werden rekursiv mitgeprueft; Fehler darin erscheinen mit dem Zusatz
`In Funktion "..."`.

Die Logik ist identisch in `pap_editor.py` (Desktop, Funktion `evaluate_chart`)
und `web/static/pap.js` (Browser, Funktion `evaluateChart`) implementiert.
Beide Dateien muessen bei Aenderungen im Regelwerk zusammen aktualisiert
werden.

Regelgruppen:

| Gruppe | Beispiele |
|---|---|
| A. Grundstruktur | genau ein Start, mindestens ein Stop, Erreichbarkeit, Zusammenhang (`R01`-`R06`) |
| B. Verbindungen/Grade | keine haengenden Pfeile, Ein-/Ausgangsgrad je Blocktyp, keine Duplikate (`R08`-`R12`) |
| C. Geometrie | Pfeile unten raus/oben rein, Verzweigungszweige, Kreuzungen, Ueberlappungen (`R14`,`R15`,`R17`-`R19`) |
| D. Kontrollstrukturen | Verzweigung/Schleife sauber geoeffnet und geschlossen, keine leeren Zweige, Endlosschleifen-Heuristik (`R20`,`R22`,`R23`,`R25`,`R26`) |
| E. Kantenbeschriftung | Ja/Nein an Verzweigungen, sonst nirgends (`R27`,`R28`) |
| F. Inhalte | Beschriftungspflicht, Bedingung in Verzweigungen, Zuweisung in Anweisungen, Variablen vor Gebrauch zugewiesen, Ausgabe auf jedem Pfad, gueltige Funktionsreferenz (`R29`-`R31`,`R33`-`R36`) |

Einige Regeln des allgemeinen Katalogs entfallen bewusst, weil es im Editor
kein passendes Konzept gibt (siehe Kommentar am Anfang des Regelwerks in
`pap_editor.py`):

- `R07` Block-IDs sind durch das Datenmodell immer eindeutig.
- `R13` es gibt keinen eigenstaendigen Seitenverweis-Konnektor.
- `R16` Schleifen haben keinen gezeichneten Ruecksprungpfeil; die Wiederholung
  ergibt sich rein aus dem Schleife/Schleife-zu-Paar.
- `R21` SESE wird nicht separat geprueft, sondern faellt bei einer Verletzung
  der Verschachtelungspruefung (`R20`/`R22`/`R23`) mit auf.
- `R32` es gibt keinen eigenen Eingabe/Ausgabe-Blocktyp; `R35` erkennt
  Ausgaben stattdessen heuristisch anhand von Schluesselwoertern.

### Eine neue Regel ergaenzen

1. Eine Funktion `check_rXX_...(nodes, ...)` schreiben (Python) bzw.
   `checkRXX...(nodesObj, ...)` (JavaScript), die eine Liste von Findings
   zurueckgibt: `{rule, severity, message, node_ids/nodeIds, arrow_ids/arrowIds}`.
2. Den Aufruf in `evaluate_chart` (Python) und `evaluateChart` (JavaScript)
   ergaenzen.
3. Die Regel-ID mit Schweregrad in der `RULES`-Tabelle in `pap_editor.py`
   nachtragen.
4. Beide Implementierungen mit dem gleichen Testdiagramm gegenpruefen, damit
   Desktop- und Web-Version dieselben Meldungen liefern.

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
