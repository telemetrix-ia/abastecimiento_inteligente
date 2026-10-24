"""Estado de una sesión de demo, auditoría forense encadenada, log técnico y créditos.

Portado de la celda 3.1 del notebook AGENTE_ABASTECIMIENTO_INTELIGENTE.ipynb.
Diferencia clave: en Vercel cada petición puede caer en una instancia distinta, así que el estado
completo de la demo (datos, órdenes, eventos, auditoría) se guarda como un documento JSON por sesión
en Upstash Redis. Sin Redis configurado se usa un archivo local (desarrollo) o memoria.
"""
import copy
import hashlib
import json
import os
import re
import secrets
import time
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import datos

TTL_SEGUNDOS = 7 * 24 * 3600          # una demo vive 7 días sin uso
MAX_AUDITORIA = 600                   # se conserva la ventana más reciente (la cadena se verifica sobre ella)
MAX_LOG = 300
RE_DEMO_ID = re.compile(r"^[a-zA-Z0-9-]{8,64}$")


# ─────────────────────────────────────────────────────────────── almacenamiento
class AlmacenUpstash:
    """Upstash Redis por REST (sin dependencias). Acepta las variables de Upstash o las de Vercel KV."""
    nombre = "upstash"

    def __init__(self, url, token):
        self.url, self.token = url.rstrip("/"), token

    def _cmd(self, *args):
        req = urllib.request.Request(self.url, data=json.dumps(list(args)).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode()).get("result")

    def leer(self, clave):
        valor = self._cmd("GET", clave)
        return json.loads(valor) if valor else None

    def guardar(self, clave, valor):
        self._cmd("SET", clave, json.dumps(valor, ensure_ascii=False, default=str), "EX", TTL_SEGUNDOS)


class AlmacenArchivo:
    """Un archivo JSON por sesión. En local es persistente; en Vercel (/tmp) es temporal por instancia."""
    nombre = "archivo"

    def __init__(self, carpeta):
        self.carpeta = carpeta
        os.makedirs(carpeta, exist_ok=True)

    def _ruta(self, clave):
        return os.path.join(self.carpeta, hashlib.sha256(clave.encode()).hexdigest()[:24] + ".json")

    def leer(self, clave):
        try:
            with open(self._ruta(clave), encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def guardar(self, clave, valor):
        tmp = self._ruta(clave) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(valor, f, ensure_ascii=False, default=str)
        os.replace(tmp, self._ruta(clave))


def crear_almacen():
    url = os.environ.get("UPSTASH_REDIS_REST_URL") or os.environ.get("KV_REST_API_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN") or os.environ.get("KV_REST_API_TOKEN")
    if url and token:
        return AlmacenUpstash(url, token)
    carpeta = "/tmp/abastecimiento-demo" if os.environ.get("VERCEL") else os.path.join(os.path.dirname(__file__), "..", ".estado")
    return AlmacenArchivo(carpeta)


ALMACEN = crear_almacen()


def clave_sesion(demo_id: str) -> str:
    if not RE_DEMO_ID.match(demo_id or ""):
        raise ValueError("demo_id inválido")
    return f"abastecimiento:demo:{demo_id}"


# ─────────────────────────────────────────────────────────────── estado inicial
def _hash_pin(pin: str, sal: str) -> str:
    return hashlib.sha256((sal + ":" + pin).encode()).hexdigest()


def estado_inicial(tablas=None) -> dict:
    """Escenario del notebook: 22/10/2026 19:00, 9 quiebres en cola, 3 órdenes previas en tránsito."""
    t = copy.deepcopy(tablas or datos.semilla())
    cfg = t["CONFIGURACION"]
    cfg.setdefault("tope_aprobacion", 250.0)
    sal = secrets.token_hex(8)
    S = {
        "version": 1,
        "tenant": t["TENANT"],
        "config": cfg,
        "costos_creditos": t["COSTOS_CREDITOS"],
        "datos": {k: t[k] for k in ("SUCURSALES", "ALMACENES", "USUARIOS", "PROVEEDORES", "PRODUCTOS", "STOCK",
                                    "VENTAS_DIARIAS", "COMPRAS_HISTORICAS")},
        "reloj": f"{t['FECHA_REFERENCIA']}T19:00:00",
        "eventos": t["EVENTOS_QUIEBRE"],
        "ocs": datos.ordenes_iniciales(t),
        "contador_oc": 0,
        "propuestas": {},
        "idempotencia": {},
        "usage_events": [],
        "saldo_creditos": cfg["saldo_creditos"],
        "consultas_por_usuario": {},
        "notificaciones": [],
        "auditoria": [],
        "log_tecnico": [],
        "chat": {},
        "usuario_activo": cfg.get("configurado_por", "U01"),
        "pin": {"sal": sal, "hash": _hash_pin(os.environ.get("DEMO_PIN", "1234"), sal), "intentos": 0, "bloqueado_hasta": 0},
        "otp": None,
        "whatsapp_simulado": [],
        "simulacion_semilla": 7,
        "origen_datos": "semilla del notebook" if tablas is None else "Excel cargado",
        "ciclo": {"vueltas": 0, "ultima_llegada": None, "unidades_vendidas": 0},
        "pruebas": {"deterministas": None, "casos": {}, "libres": []},
    }
    S["contador_oc"] = max([int(o["numero"].split("-")[1]) for o in S["ocs"]] + [146])
    return S


def cargar(demo_id: str) -> dict:
    S = ALMACEN.leer(clave_sesion(demo_id))
    if not S or S.get("version") != 1:
        return estado_inicial()
    S.setdefault("ciclo", {"vueltas": 0, "ultima_llegada": None, "unidades_vendidas": 0})
    S.setdefault("pruebas", {"deterministas": None, "casos": {}, "libres": []})
    return S


def guardar(demo_id: str, S: dict):
    S["auditoria"] = S["auditoria"][-MAX_AUDITORIA:]
    S["log_tecnico"] = S["log_tecnico"][-MAX_LOG:]
    for uid in S["chat"]:
        S["chat"][uid] = S["chat"][uid][-40:]
    ALMACEN.guardar(clave_sesion(demo_id), S)


# ─────────────────────────────────────────────────────────────── reloj simulado
def zona(S):
    return ZoneInfo(S["tenant"]["zona_horaria"])


def reloj(S) -> datetime:
    return datetime.fromisoformat(S["reloj"]).replace(tzinfo=zona(S))


def reloj_iso(S) -> str:
    return reloj(S).isoformat(timespec="seconds")


def avanzar_reloj(S, horas: float):
    S["reloj"] = (reloj(S) + timedelta(hours=horas)).replace(tzinfo=None).isoformat(timespec="seconds")


# ─────────────────────────────────────────────────────────────── contexto de petición
def nuevo_contexto(S, modo: str, usuario_id: str) -> dict:
    es_corrida = modo in ("programada", "a_demanda")
    return {
        "request_id": "REQ-" + secrets.token_hex(6),
        "corrida_id": ("CRR-" + secrets.token_hex(5)) if es_corrida else None,
        "modo": modo,
        "usuario_id": usuario_id,
        "actor_tipo": "AGENTE" if modo == "programada" else "USUARIO",
        "actor_id": "agente:abastecimiento" if modo == "programada" else usuario_id,
        "canal": {"programada": "scheduler", "a_demanda": "app-ai", "consulta": "app-ai"}.get(modo, "app-purchase"),
        "borradores_creados": [], "lineas_excluidas": [], "propuesta_id": None,
        "alertas": [], "auditoria_ids": [], "denegaciones": [],
    }


# ─────────────────────────────────────────────────────────────── auditoría (core-audit)
def _hash_registro(registro: dict) -> str:
    cuerpo = {k: v for k, v in registro.items() if k != "hash"}
    return hashlib.sha256(json.dumps(cuerpo, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def auditar(S, C, accion, resultado="OK", recurso=None, detalle=None, severidad="BAJA", actor_tipo=None, actor_id=None):
    """Registro forense encadenado por hash. severidad BAJA / MEDIA / ALTA."""
    numero = (int(S["auditoria"][-1]["audit_id"].split("-")[1]) + 1) if S["auditoria"] else 1
    registro = {
        "audit_id": f"AUD-{numero:05d}",
        "ts": reloj_iso(S), "ts_real": datetime.now(zona(S)).isoformat(timespec="seconds"),
        "tenant_id": S["tenant"]["tenant_id"],
        "actor_tipo": actor_tipo or C.get("actor_tipo", "SISTEMA"),
        "actor_id": actor_id or C.get("actor_id", "sistema"),
        "en_nombre_de": C.get("usuario_id"), "canal": C.get("canal"), "modo": C.get("modo"),
        "request_id": C.get("request_id"), "corrida_id": C.get("corrida_id"),
        "accion": accion, "recurso": recurso, "resultado": resultado, "severidad": severidad,
        "detalle": detalle or {},
        "prev_hash": S["auditoria"][-1]["hash"] if S["auditoria"] else "0" * 64,
    }
    registro["hash"] = _hash_registro(registro)
    S["auditoria"].append(registro)
    C.setdefault("auditoria_ids", []).append(registro["audit_id"])
    return registro["audit_id"]


def verificar_cadena(registros) -> bool:
    if not registros:
        return True
    previo = registros[0]["prev_hash"]
    for r in registros:
        if r["prev_hash"] != previo or _hash_registro(r) != r["hash"]:
            return False
        previo = r["hash"]
    return True


# ─────────────────────────────────────────────────────────────── log técnico (core-observabilidad)
CAMPOS_LOG = {"componente", "herramienta", "estado", "latencia_ms", "modelo", "largo_entrada", "sha256_entrada",
              "codigo", "error_tipo", "n_iteraciones", "n_tools", "ruta", "metodo", "status"}


def log_tecnico(S, C, evento, nivel="INFO", **campos):
    """Solo campos de la lista blanca: nunca texto del usuario, PIN ni datos de negocio."""
    S["log_tecnico"].append({"ts": datetime.now(zona(S)).isoformat(timespec="seconds"), "nivel": nivel,
                             "evento": evento, "tenant_id": S["tenant"]["tenant_id"],
                             "request_id": C.get("request_id"), "corrida_id": C.get("corrida_id"),
                             **{k: v for k, v in campos.items() if k in CAMPOS_LOG}})


# ─────────────────────────────────────────────────────────────── créditos y notificaciones
def cobrar_creditos(S, C, operacion, idempotency_key, ref_id) -> int:
    if any(e["idempotency_key"] == idempotency_key for e in S["usage_events"]):
        return 0
    costo = S["costos_creditos"][operacion]
    S["saldo_creditos"] -= costo
    S["usage_events"].append({"metric": "ai_credit", "operacion": operacion, "creditos": costo,
                              "idempotency_key": idempotency_key, "ref_id": ref_id, "ts": reloj_iso(S)})
    auditar(S, C, "CONSUMO_CREDITOS", recurso=ref_id,
            detalle={"operacion": operacion, "creditos": costo, "saldo_despues": S["saldo_creditos"]})
    return costo


def notificar(S, C, mensaje, enlace=None, para="Administrador"):
    S["notificaciones"].insert(0, {"id": secrets.token_hex(4), "ts": reloj_iso(S), "para": para, "mensaje": mensaje,
                                   "enlace": enlace, "leida": False, "corrida_id": C.get("corrida_id")})
    S["notificaciones"] = S["notificaciones"][:30]
    return mensaje


def ahora_epoch() -> float:
    return time.time()
