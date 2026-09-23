# Web-Version auf den Server bringen

Die Web-Version laeuft in zwei Betriebsarten. Welche du brauchst, entscheidet
nur der Menuepunkt „Desktop-Version" – der Editor selbst funktioniert immer.

## A) Statisch (z. B. Plesk/nginx, nur Dateien hochladen)

Hochzuladen aus `web/static/`:

```
index.html
pap.js
pap.css
favicon.svg
favicon-32.png
apple-touch-icon.png
.htaccess        <- versteckte Datei! im FTP-Programm sichtbar schalten
```

Der Editor laeuft damit vollstaendig. Der Download-Dialog fragt die GitHub-API
direkt aus dem Browser ab (`GITHUB_REPO` oben in `pap.js`). **Das klappt nur bei
einem oeffentlichen Repository** – ist es privat, antwortet GitHub dem Browser
mit 404 und der Dialog faellt auf die Dateien in `downloads/` zurueck, sofern du
welche hochlaedst.

## B) Mit Flask-Backend (`python3 web/app.py`)

Zusaetzlich laeuft `/api/downloads` und `/downloads/latest/...`. Dann
funktioniert der Download auch bei **privatem** Repository, weil das Token auf
dem Server bleibt:

```bash
export PAP_GITHUB_TOKEN=github_pat_...
bash web/start_web.sh
```

## Nach jedem Update unbedingt beachten

1. In `index.html` den Cache-Buster hochzaehlen (`pap.css?v=N`, `pap.js?v=N`).
2. **Alle drei Dateien zusammen** hochladen. Eine alte `index.html` mit einer
   neuen `pap.js` ist die haeufigste Fehlerquelle: frueher blieb die Seite dabei
   komplett leer. Heute laeuft der Editor trotzdem und blendet oben einen
   gelben Hinweis „bitte mit Strg+F5 neu laden" ein.
3. Einmal hart neu laden (Strg+F5 / ⌘+Shift+R), sonst zeigt der eigene Browser
   weiter die alte Seite.
