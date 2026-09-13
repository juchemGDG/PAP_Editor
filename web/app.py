"""Flask-Backend für den PAP-Editor Web-Client.

Startet auf http://0.0.0.0:5000 und ist damit im lokalen Netz
(z. B. vom iPad) über die IP-Adresse des Macs erreichbar.

Zusätzlich vermittelt das Backend die Downloads der Desktop-Version: es fragt
das neueste GitHub-Release ab und leitet auf die passende Datei weiter. Damit
müssen die Pakete nicht mehr von Hand auf den Server kopiert werden. Liegt eine
Datei lokal in static/downloads/, wird sie als Rückfallebene genutzt.
"""

import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

from flask import Flask, abort, jsonify, redirect, send_from_directory

app = Flask(__name__, static_folder="static", static_url_path="")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BILDER_DIR = os.path.join(BASE_DIR, "..", "Bilder")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "static", "downloads")

# ── Desktop-Downloads ───────────────────────────────────────────────────
# Repository und (optional) Token per Umgebungsvariable überschreibbar:
#   PAP_GITHUB_REPO=benutzer/repo   PAP_GITHUB_TOKEN=ghp_...
# Ein Token wird nur für ein privates Repository gebraucht; es bleibt auf dem
# Server und taucht nie im Browser auf.
GITHUB_REPO = os.environ.get("PAP_GITHUB_REPO", "juchemGDG/PAP_Editor")
GITHUB_TOKEN = os.environ.get("PAP_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""

# Reihenfolge im Dialog. Die Dateinamen müssen mit den Assets des Releases
# übereinstimmen (siehe .github/workflows/build-packages.yml).
DESKTOP_ASSETS = [
    ("macos",   "macOS",   "PAP-Editor.dmg",                 "Apple Silicon & Intel · .dmg"),
    ("windows", "Windows", "PAP-Editor-Setup.exe",           "Installer · .exe"),
    ("linux",   "Linux",   "PAP-Editor-linux-x86_64.tar.gz", "entpacken & starten · .tar.gz"),
]

CACHE_OK_SECONDS = 300      # erfolgreiche Abfrage 5 Minuten cachen
CACHE_FAIL_SECONDS = 60     # nach einem Fehler nicht dauernd neu anfragen
_release_cache = {"time": 0.0, "data": None, "error": None}


class _NoRedirect(HTTPRedirectHandler):
    """Weiterleitungen nicht selbst folgen – wir wollen die Ziel-URL sehen."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _gh_headers(accept):
    headers = {"Accept": accept, "User-Agent": "PAP-Editor"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def _latest_release():
    """Neuestes Release von GitHub holen (mit kleinem Cache)."""
    now = time.time()
    age = now - _release_cache["time"]
    if _release_cache["data"] is not None and age < CACHE_OK_SECONDS:
        return _release_cache["data"], None
    if _release_cache["error"] is not None and age < CACHE_FAIL_SECONDS:
        return None, _release_cache["error"]

    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    try:
        with urlopen(Request(url, headers=_gh_headers("application/vnd.github+json")), timeout=6) as response:
            data = json.load(response)
        _release_cache.update(time=now, data=data, error=None)
        return data, None
    except HTTPError as exc:
        error = "kein Release gefunden" if exc.code == 404 else f"GitHub antwortet mit {exc.code}"
        if exc.code in (401, 403, 404) and not GITHUB_TOKEN:
            error += " (privates Repository? PAP_GITHUB_TOKEN setzen)"
    except (URLError, ValueError, OSError) as exc:
        error = f"GitHub nicht erreichbar ({exc})"
    _release_cache.update(time=now, data=None, error=error)
    return None, error


def _assets_by_name(release):
    return {asset.get("name"): asset for asset in (release or {}).get("assets", [])}


def _local_size(name):
    path = os.path.join(DOWNLOADS_DIR, name)
    return os.path.getsize(path) if os.path.isfile(path) else None


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/bilder/<path:filename>")
def bilder(filename):
    """Stellt die PAP-Block-PNGs aus dem Bilder/-Verzeichnis bereit."""
    safe = os.path.basename(filename)
    return send_from_directory(BILDER_DIR, safe)


@app.route("/api/downloads")
def api_downloads():
    """Was steht zum Download bereit? Zuerst GitHub-Release, sonst lokale Datei."""
    release, error = _latest_release()
    assets = _assets_by_name(release)

    files = []
    for key, os_name, filename, hint in DESKTOP_ASSETS:
        asset = assets.get(filename)
        local = _local_size(filename)
        if asset:
            files.append({"key": key, "os": os_name, "name": filename, "hint": hint,
                          "url": f"downloads/latest/{key}", "size": asset.get("size"),
                          "source": "github", "available": True})
        elif local is not None:
            files.append({"key": key, "os": os_name, "name": filename, "hint": hint,
                          "url": f"downloads/{filename}", "size": local,
                          "source": "lokal", "available": True})
        else:
            files.append({"key": key, "os": os_name, "name": filename, "hint": hint,
                          "url": None, "size": None, "source": None, "available": False})

    published = (release or {}).get("published_at") or ""
    return jsonify({
        "repo": GITHUB_REPO,
        "version": (release or {}).get("tag_name"),
        "published": published[:10],
        "release_url": (release or {}).get("html_url"),
        "error": error,
        "files": files,
    })


@app.route("/downloads/latest/<key>")
def download_latest(key):
    """Leitet auf die Datei des neuesten Releases weiter (sonst auf die lokale Kopie)."""
    entry = next((item for item in DESKTOP_ASSETS if item[0] == key), None)
    if entry is None:
        abort(404)
    filename = entry[2]

    release, _ = _latest_release()
    asset = _assets_by_name(release).get(filename)
    if asset:
        # Über die API-URL laden: funktioniert auch bei privatem Repository.
        # GitHub antwortet mit einer kurzlebigen, signierten Download-URL.
        request = Request(asset["url"], headers=_gh_headers("application/octet-stream"))
        try:
            opener = build_opener(_NoRedirect)
            with opener.open(request, timeout=6) as response:
                location = response.headers.get("Location")
            if location:
                return redirect(location)
        except HTTPError as exc:
            location = exc.headers.get("Location") if exc.headers else None
            if location:
                return redirect(location)
        except (URLError, OSError):
            pass
        if asset.get("browser_download_url"):     # öffentliches Repository
            return redirect(asset["browser_download_url"])

    if os.path.isfile(os.path.join(DOWNLOADS_DIR, filename)):
        return redirect(f"/downloads/{filename}")
    abort(404)


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    print(f"\n  PAP Editor läuft auf  http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
