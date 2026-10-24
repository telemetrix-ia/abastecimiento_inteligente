"""Servidor local: sirve public/ y enruta /api/* al mismo backend que usa Vercel.

    pip install -r requirements.txt
    export OPENROUTER_API_KEY=...       # opcional: sin clave usa la IA simulada
    python dev_server.py                # http://localhost:8000
"""
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

RAIZ = os.path.dirname(os.path.abspath(__file__))


def cargar_env(ruta=os.path.join(RAIZ, ".env")):
    """Lee .env (CLAVE=valor). Ignora comentarios, comillas y espacios; no pisa variables ya definidas en la terminal."""
    if not os.path.exists(ruta):
        return []
    cargadas = []
    with open(ruta, encoding="utf-8-sig") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, valor = linea.split("=", 1)
            clave = clave.strip().removeprefix("export ").strip()
            valor = valor.split(" #")[0].split("\t#")[0].strip().strip('"').strip("'")
            if clave and valor and clave not in os.environ:
                os.environ[clave] = valor
                cargadas.append(clave)
    return cargadas


CARGADAS = cargar_env()
sys.path.insert(0, RAIZ)
from backend.api import manejar  # noqa: E402


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=os.path.join(RAIZ, "public"), **k)

    def _api(self, metodo):
        largo = int(self.headers.get("Content-Length") or 0)
        status, cab, cuerpo = manejar(metodo, self.path, dict(self.headers), self.rfile.read(largo) if largo else b"")
        self.send_response(status)
        for k, v in cab.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._api("GET")
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            return self._api("POST")
        self.send_error(404)

    def log_message(self, fmt, *args):
        if "/api/" in (args[0] if args else ""):
            sys.stderr.write("%s\n" % (fmt % args))


if __name__ == "__main__":
    puerto = int(os.environ.get("PORT", "8000"))
    clave = os.environ.get("OPENROUTER_API_KEY", "")
    if CARGADAS:
        print("Variables leídas de .env:", ", ".join(CARGADAS))
    if clave:
        print(f"OPENROUTER_API_KEY detectada ({clave[:8]}…{clave[-4:]}) · modelo {os.environ.get('OPENROUTER_MODEL', 'nvidia/nemotron-3-ultra-550b-a55b:free')}")
        if not clave.startswith("sk-or-"):
            print("  Aviso: las claves de OpenRouter empiezan con «sk-or-». Revisa que copiaste la clave correcta.")
        if os.environ.get("MODO_IA") == "simulado":
            print("  Aviso: MODO_IA=simulado fuerza la IA simulada aunque haya clave.")
    else:
        print("Sin OPENROUTER_API_KEY: la demo usará la IA simulada. Ponla en el archivo .env junto a este script.")
    print(f"Demo en http://localhost:{puerto}")
    ThreadingHTTPServer(("0.0.0.0", puerto), Handler).serve_forever()
