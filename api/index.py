"""Función serverless de Vercel (runtime Python). Todas las rutas /api/* llegan aquí (ver vercel.json)."""
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.api import manejar  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def _responder(self, metodo):
        largo = int(self.headers.get("Content-Length") or 0)
        cuerpo = self.rfile.read(largo) if largo else b""
        status, cabeceras, salida = manejar(metodo, self.path, dict(self.headers), cuerpo)
        self.send_response(status)
        for k, v in cabeceras.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(salida)))
        self.end_headers()
        self.wfile.write(salida)

    def do_GET(self):
        self._responder("GET")

    def do_POST(self):
        self._responder("POST")

    def log_message(self, *args):
        pass
