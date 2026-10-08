# PAP Editor

Ein kleines Tkinter-Applet zum schnellen Erstellen von Programmablaufplaenen.

## Funktionen

- Bausteine aus dem Ordner `Bilder/` per Drag and Drop auf die Flaeche ziehen
- Inhalte per Doppelklick aendern, mehrzeilig mit Strg/Cmd+Enter (oder Shift+Enter);
  das gilt auch fuer den Baustein "Funktion"
- Rechtsklick auf einen "Funktion"-Baustein (auf dem iPad: langes Tippen) oeffnet
  ein Menue, ueber das sich der Unterablaufplan oeffnen oder der Block loeschen
  laesst
- Blockbreite frei einstellbar: Anfasser rechts unten ziehen, mehrere Bloecke
  mit "Breite angleichen" (Strg/Cmd+B) auf dieselbe Breite bringen;
  Strg/Cmd+Shift+B stellt die automatische Breite wieder her. Das gilt fuer
  alle Bausteine inkl. "Schleife zu" – nur der runde "Verzweigung zu"-Punkt
  behaelt seine Form
- Pfeile per Maus zwischen Symbolen ziehen, auch als Ruecksprung zu einem
  weiter oben liegenden Block (der Pfeil muendet dann immer von oben ein)
- Verzweigung schliessen: der rechte Zweig muendet von rechts in "Verzweigung zu"
  – auch ein leerer Zweig direkt aus der Raute. Wird der Pfeil auf dem rechten
  bzw. oberen Anschlusspunkt losgelassen, wird genau dieser verwendet; die
  Vorschau zeigt den Anschluss schon beim Ziehen
- Schriftgroesse je Block: Bloecke markieren, dann "A−" / "A+" in der
  Menueleiste (wird in der JSON-Datei als `font_size`/`fontSize` gespeichert)
- Button "Hilfe & Bedienung" unten in der linken Leiste oeffnet die komplette Bedienung
  in gut lesbarer Schrift
- Knickpunkte: markierten Pfeil anklicken setzt einen Knick, Ziehen verschiebt
  ihn am Raster, Doppel-/Rechtsklick auf den Knick entfernt ihn
- Speichern und Laden als JSON
- Export als PNG und JPG
- Informationsfluss: hellblauer Baustein "Infofluss" links neben dem Start, verbunden
  per Pfeil an die linke Seite des Starts. Doppelklick oeffnet den IBD-Editor
  (siehe unten "Informationsfluss (IBD)")
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
| C. Geometrie | Pfeile unten raus/oben rein, Ruecksprung zu einer Schleife (Hinweis), Verzweigungszweige, Kreuzungen, Ueberlappungen (`R14`-`R19`) |
| D. Kontrollstrukturen | Verzweigung/Schleife sauber geoeffnet und geschlossen, keine leeren Zweige, Endlosschleifen-Heuristik (`R20`,`R22`,`R23`,`R25`,`R26`) |
| E. Kantenbeschriftung | Ja/Nein an Verzweigungen, sonst nirgends (`R27`,`R28`) |
| F. Inhalte | Beschriftungspflicht, Bedingung in Verzweigungen, Zuweisung in Anweisungen, gueltige Funktionsreferenz (`R29`-`R31`,`R36`) |

`R16` deckt den von Hand gezeichneten Ruecksprung ab: ein Pfeil von einem
`Schleife zu`-Block an einen weiter oben liegenden `Schleife`-Block ist
erlaubt und erzeugt nur einen Hinweis. Jeder andere Pfeil nach oben bleibt
ein `R17`-Hinweis.

Einige Regeln des allgemeinen Katalogs entfallen bewusst, weil es im Editor
kein passendes Konzept gibt (siehe Kommentar am Anfang des Regelwerks in
`pap_editor.py`):

- `R07` Block-IDs sind durch das Datenmodell immer eindeutig.
- `R13` es gibt keinen eigenstaendigen Seitenverweis-Konnektor.
- `R21` SESE wird nicht separat geprueft, sondern faellt bei einer Verletzung
  der Verschachtelungspruefung (`R20`/`R22`/`R23`) mit auf.
- `R32` es gibt keinen eigenen Eingabe/Ausgabe-Blocktyp.
- `R33`-`R35` (Ein-Anweisung-pro-Block, Datenfluss-Analyse, Ausgabe auf jedem
  Pfad) sind bewusst deaktiviert, da sie bei kurzen Schul-Beispielen zu viele
  Fehlalarme erzeugt haben.

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

## Informationsfluss (IBD)

Der Baustein "Infofluss" verknuepft den PAP mit einem Informationsfluss-
Blockdiagramm aus dem IBD-Editor (https://ibd.mint-checker.de, `?embed=1`).

- Er hat nur einen Anschluss rechts und laesst sich nur mit der linken Seite des
  Start-Blocks verbinden. Die Plausibilitaetspruefung blendet ihn samt Pfeil aus.
- Doppelklick (oder Rechtsklick -> "Informationsfluss oeffnen ...") oeffnet den
  IBD-Editor; "In Projekt uebernehmen" speichert am Block `ibd` (IBD-Datei),
  `ibdSvg`/`ibd_svg` und `ibdPng`/`ibd_png` (PNG als data:-URL, damit auch die
  Desktop-Version ohne SVG-Renderer exportieren kann).
- Speichern legt zusaetzlich `<name>_ibd.json` ab (im IBD-Editor ladbar),
  PNG/JPG/SVG-Export zusaetzlich `<name>_ibd.png|jpg|svg`. Bei mehreren
  Infofluss-Bloecken: `_ibd_2`, `_ibd_3` ...
- Web: Der IBD-Editor laeuft als iframe-Overlay ueber dem PAP (gleiches
  postMessage-Protokoll wie unten, Quelle `ibd-editor`, Origin wird geprueft).
- Desktop: Tkinter kann keine Webseite anzeigen. Der Editor startet daher einen
  kleinen Webserver auf `127.0.0.1` (zufaelliger Port, zufaelliges Token je
  Sitzung) und oeffnet im Standardbrowser eine Seite, die den IBD-Editor einbettet
  und das Ergebnis per POST zurueckschickt (`IbdBridge` in `pap_editor.py`).
  Dafuer ist eine Internetverbindung noetig.
- Im Einbettungsmodus (`?embed=1`) gibt es den Baustein nicht.

## Einbettung in andere Web-Apps (`?embed=1`)

Die Web-Version kann per iframe eingebettet werden (z. B. vom Projektmanagement-Tool,
Aufgabenansicht). Mit `?embed=1` erscheinen die Buttons "In Projekt uebernehmen" und
"Schliessen", der Download-Hinweis auf die Desktop-Version entfaellt.

Protokoll ueber `window.postMessage` (in `web/static/pap.js`, Abschnitt "Einbettung"):

| Richtung | Nachricht |
|---|---|
| Editor -> Host | `{source:'pap-editor', event:'ready'}` |
| Host -> Editor | `{target:'pap-editor', action:'load', diagram:<JSON wie "Speichern" oder null>, title, downloads:true}` |
| Editor -> Host | `{source:'pap-editor', event:'save', diagram:<JSON>, svg:<SVG-Text>}` |
| Editor -> Host | `{source:'pap-editor', event:'exit'}` |
| Editor -> Host | `{source:'pap-editor', event:'download', name, mime, blob:<Blob>}` |

Downloads (Speichern, PNG, JPG, SVG) blockieren Browser im iframe oft – bei
`sandbox` ohne `allow-downloads` und in Safari bei fremder Origin. Schickt der Host
in `load` den Schalter `downloads:true`, uebergibt der Editor die Datei stattdessen
per `download`-Nachricht, und der Host speichert sie selbst:

```js
if (e.data.event === 'download') {
  const url = URL.createObjectURL(e.data.blob);
  const a = Object.assign(document.createElement('a'), { href: url, download: e.data.name });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
```

Ohne `downloads:true` versucht der Editor den Download wie bisher selbst.

Der Editor nimmt nur Nachrichten seines Eltern-Fensters an und schickt Diagrammdaten
nur an dessen Origin. Der Host sollte umgekehrt `event.origin` und `event.source` pruefen.

