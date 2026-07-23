"""Flask-Backend für den PAP-Editor Web-Client.

Startet auf http://0.0.0.0:5000 und ist damit im lokalen Netz
(z. B. vom iPad) über die IP-Adresse des Macs erreichbar.
"""

import os
from flask import Flask, send_from_directory

app = Flask(__name__, static_folder="static", static_url_path="")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BILDER_DIR = os.path.join(BASE_DIR, "..", "Bilder")


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/bilder/<path:filename>")
def bilder(filename):
    """Stellt die PAP-Block-PNGs aus dem Bilder/-Verzeichnis bereit."""
    safe = os.path.basename(filename)
    return send_from_directory(BILDER_DIR, safe)


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    print(f"\n  PAP Editor läuft auf  http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
