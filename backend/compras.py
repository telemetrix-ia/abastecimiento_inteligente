"""Ciclo de la Orden de Compra (W-PURCHASE-01 y S-10): editar el borrador, enviar a aprobación con tope,
aprobar, rechazar, deshacer y enviar al proveedor con PIN u OTP de contingencia.

El PIN se valida solo aquí, en el servidor, contra un hash con sal. Nunca viaja al modelo ni a los logs.
"""
import hashlib
import hmac
import secrets
from datetime import timedelta

from . import motor
from .datos import CONDICION_PAGO
from .estado import ahora_epoch, auditar, notificar, nuevo_contexto, reloj, reloj_iso
from .herramientas import monto_oc
from .llm import _soles

MAX_INTENTOS_PIN = 3
BLOQUEO_SEGUNDOS = 300
OTP_SEGUNDOS = 180
ACCIONES = {"ver": "compras.ver", "editar": "compras.editar", "aprobar": "compras.aprobar", "enviar": "compras.despachar"}


class ErrorCompras(Exception):
    def __init__(self, mensaje, codigo="NO_PERMITIDO", status=409):
        super().__init__(mensaje)
        self.codigo, self.status = codigo, status


def _ctx(S, uid):
    C = nuevo_contexto(S, "consulta", uid)
    C.update({"modo": "compras", "canal": "app-purchase", "actor_tipo": "USUARIO", "actor_id": uid})
    return C


def _oc(S, numero):
    oc = next((o for o in S["ocs"] if o["numero"] == numero), None)
    if not oc:
        raise ErrorCompras(f"No existe la orden {numero}", "NO_ENCONTRADA", 404)
    return oc


def _exigir(S, uid, accion, oc=None):
    if not motor.tiene_permiso(S, uid, ACCIONES[accion]):
        raise ErrorCompras("No tienes permiso para esta acción.", "SIN_PERMISO", 403)
    if oc is not None:
        vis = motor.almacenes_visibles(S, uid)
        if not all(l["almacen_id"] in vis for l in oc["lineas"]):
            raise ErrorCompras("La orden incluye almacenes de sucursales que no tienes asignadas.", "VISIBILIDAD_CRUZADA", 403)


def _historial(S, oc, accion, actor, detalle=None):
    oc["historial"].append({"ts": reloj_iso(S), "accion": accion, "actor": actor, **({"detalle": detalle} if detalle else {})})


def acciones_posibles(S, uid, oc) -> dict:
    """Qué puede hacer el usuario con esta orden y, si no puede, por qué (para deshabilitar con explicación)."""
    def p(accion):
        return motor.tiene_permiso(S, uid, ACCIONES[accion])
    e = oc["estado"]
    r = {}
    if e == "BORRADOR":
        r["editar"] = (p("editar"), None if p("editar") else "Sin permiso para editar")
        motivo = None
        if not p("editar"):
            motivo = "Sin permiso"
        elif oc["sin_proveedor_asignado"] or not oc["proveedor_id"]:
            motivo = "Elige un proveedor antes de enviarla"
        elif any(l["costo_unitario"] is None for l in oc["lineas"]):
            motivo = "Completa el costo de cada línea"
        r["enviar_aprobacion"] = (motivo is None, motivo)
    if e == "PENDIENTE_APROBACION":
        motivo = None if p("aprobar") else "Sin permiso para aprobar"
        if motivo is None and oc["creada_por"] == uid:
            motivo = "La creaste tú: la aprueba otra persona"
        r["aprobar"] = (motivo is None, motivo)
        r["rechazar"] = (motivo is None, motivo)
    if e == "APROBADA" and not oc["enviada_al_proveedor"]:
        r["enviar_proveedor"] = (p("enviar"), None if p("enviar") else "Solo el Administrador puede enviarla con su PIN")
        r["deshacer_aprobacion"] = (p("aprobar"), None)
    if e in ("APROBADA", "RECIBIDA_PARCIAL") and oc["enviada_al_proveedor"]:
        r["recibir"] = (False, "La recepción (W-PURCHASE-04) está fuera de esta demo; usa «Simular llegada» en el Panel de demo")
    return {k: {"permitido": v[0], "motivo": v[1]} for k, v in r.items()}


# ─────────────────────────────────────────────────────────────── edición del borrador
def editar_linea(S, uid, numero, sku, almacen_id, cantidad=None, costo_unitario=None, quitar=False):
    oc = _oc(S, numero)
    _exigir(S, uid, "editar", oc)
    if oc["estado"] != "BORRADOR":
        raise ErrorCompras("Solo se edita en Borrador.", "ESTADO_INVALIDO")
    linea = next((l for l in oc["lineas"] if l["sku"] == sku and l["almacen_id"] == almacen_id), None)
    if not linea:
        raise ErrorCompras("La línea no existe.", "NO_ENCONTRADA", 404)
    C = _ctx(S, uid)
    if quitar:
        if len(oc["lineas"]) == 1:
            raise ErrorCompras("La orden necesita al menos una línea.", "VALIDACION", 422)
        oc["lineas"].remove(linea)
        _historial(S, oc, f"Quitó {sku}", uid)
        auditar(S, C, "OC_QUITAR_LINEA", recurso=numero, detalle={"sku": sku, "almacen_id": almacen_id})
        return oc
    cambios = {}
    if cantidad is not None:
        cantidad = int(cantidad)
        if not 1 <= cantidad <= 9999:
            raise ErrorCompras("La cantidad debe estar entre 1 y 9.999.", "VALIDACION", 422)
        if cantidad != linea["cantidad"]:
            cambios["cantidad"] = [linea["cantidad"], cantidad]
            linea["cantidad"] = cantidad
    if costo_unitario is not None:
        if not motor.tiene_permiso(S, uid, "costos.ver"):
            raise ErrorCompras("No tienes permiso para ver ni editar costos.", "SIN_PERMISO", 403)
        costo = round(float(costo_unitario), 2)
        if not 0 < costo <= 100000:
            raise ErrorCompras("El costo debe ser mayor que 0.", "VALIDACION", 422)
        cambios["costo_unitario"] = [linea["costo_unitario"], costo]
        linea["costo_unitario"] = costo
    if cambios:
        texto = []
        if "cantidad" in cambios:
            texto.append(f"cantidad de {sku}: {cambios['cantidad'][0]} → {cambios['cantidad'][1]} (sugerida {linea['sugerida']})" if linea["sugerida"]
                         else f"cantidad de {sku}: {cambios['cantidad'][0]} → {cambios['cantidad'][1]}")
        if "costo_unitario" in cambios:
            texto.append(f"costo de {sku}")
        _historial(S, oc, "Editó " + " y ".join(texto), uid)
        auditar(S, C, "OC_EDITAR_LINEA", recurso=numero, detalle={"sku": sku, "almacen_id": almacen_id, "cambios": cambios,
                                                                  "origen_agente": oc["origen"] == "AGENTE"})
    return oc


def asignar_proveedor(S, uid, numero, proveedor_id):
    oc = _oc(S, numero)
    _exigir(S, uid, "editar", oc)
    if oc["estado"] != "BORRADOR":
        raise ErrorCompras("Solo se edita en Borrador.", "ESTADO_INVALIDO")
    if proveedor_id not in motor.idx(S)["prov"]:
        raise ErrorCompras("Proveedor inexistente.", "VALIDACION", 422)
    oc["proveedor_id"] = proveedor_id
    oc["sin_proveedor_asignado"] = False
    oc["condicion_pago"] = CONDICION_PAGO.get(proveedor_id, "Contado")
    for l in oc["lineas"]:
        if l["costo_unitario"] is None:
            previas = sorted((c for c in S["datos"]["COMPRAS_HISTORICAS"] if c["sku"] == l["sku"] and c["proveedor_id"] == proveedor_id),
                             key=lambda c: c["fecha"])
            if previas:
                l["costo_unitario"] = previas[-1]["costo_unitario"]
    _historial(S, oc, f"Asignó el proveedor {motor.idx(S)['prov'][proveedor_id]['razon_social']}", uid)
    auditar(S, _ctx(S, uid), "OC_ASIGNAR_PROVEEDOR", recurso=numero, detalle={"proveedor_id": proveedor_id})
    return oc


# ─────────────────────────────────────────────────────────────── aprobación
def enviar_a_aprobacion(S, uid, numeros):
    tope = float(S["config"].get("tope_aprobacion") or 0)
    C = _ctx(S, uid)
    resultado = {"pendientes": [], "aprobadas": [], "omitidas": []}
    for numero in numeros:
        oc = _oc(S, numero)
        _exigir(S, uid, "editar", oc)
        accion = acciones_posibles(S, uid, oc).get("enviar_aprobacion")
        if not accion or not accion["permitido"]:
            resultado["omitidas"].append({"numero": numero, "motivo": (accion or {}).get("motivo") or "No está en Borrador"})
            continue
        monto = monto_oc(oc)
        oc["fecha_entrega"] = (reloj(S) + timedelta(days=5)).date().isoformat()
        if tope and monto > tope:
            oc["estado"] = "PENDIENTE_APROBACION"
            _historial(S, oc, f"Enviada a aprobación: supera el tope de {_soles(tope)}", uid)
            resultado["pendientes"].append({"numero": numero, "monto": monto})
        else:
            oc["estado"] = "APROBADA"
            _historial(S, oc, "Enviada a aprobación: bajo el tope, aprobada automáticamente", uid)
            resultado["aprobadas"].append({"numero": numero, "monto": monto})
        auditar(S, C, "OC_ENVIAR_A_APROBACION", recurso=numero, detalle={"monto": monto, "tope": tope, "estado": oc["estado"],
                                                                         "origen_agente": oc["origen"] == "AGENTE"})
    resultado["tope"] = tope
    return resultado


def aprobar(S, uid, numeros):
    C = _ctx(S, uid)
    resultado = {"aprobadas": [], "excluidas": []}
    for numero in numeros:
        oc = _oc(S, numero)
        _exigir(S, uid, "ver", oc)
        accion = acciones_posibles(S, uid, oc).get("aprobar")
        if not accion or not accion["permitido"]:
            resultado["excluidas"].append({"numero": numero, "motivo": (accion or {}).get("motivo") or "No está pendiente de aprobación"})
            continue
        oc["estado"] = "APROBADA"
        _historial(S, oc, "Aprobada", uid)
        auditar(S, C, "OC_APROBAR", recurso=numero, detalle={"monto": monto_oc(oc), "propuesta_agente": oc.get("propuesta_id")})
        resultado["aprobadas"].append(numero)
    return resultado


def deshacer_aprobacion(S, uid, numeros):
    _exigir(S, uid, "aprobar")
    for numero in numeros:
        oc = _oc(S, numero)
        if oc["estado"] == "APROBADA" and not oc["enviada_al_proveedor"]:
            oc["estado"] = "PENDIENTE_APROBACION"
            _historial(S, oc, "Deshizo la aprobación", uid)
            auditar(S, _ctx(S, uid), "OC_DESHACER_APROBACION", recurso=numero)
    return {"ok": True}


def rechazar(S, uid, numero, motivo=""):
    oc = _oc(S, numero)
    accion = acciones_posibles(S, uid, oc).get("rechazar")
    if not accion or not accion["permitido"]:
        raise ErrorCompras((accion or {}).get("motivo") or "No está pendiente de aprobación.", "NO_PERMITIDO")
    oc["estado"] = "BORRADOR"
    _historial(S, oc, "Rechazada: vuelve a Borrador", uid, (motivo or "")[:160] or None)
    auditar(S, _ctx(S, uid), "OC_RECHAZAR", recurso=numero)
    return oc


# ─────────────────────────────────────────────────────────────── PIN, OTP y envío al proveedor
def _hash(valor, sal):
    return hashlib.sha256((sal + ":" + valor).encode()).hexdigest()


def solicitar_otp(S, uid):
    _exigir(S, uid, "enviar")
    codigo = f"{secrets.randbelow(1000000):06d}"
    sal = secrets.token_hex(6)
    S["otp"] = {"hash": _hash(codigo, sal), "sal": sal, "expira": ahora_epoch() + OTP_SEGUNDOS, "usuario": uid}
    u = motor.usuario(S, uid)
    S["whatsapp_simulado"].insert(0, {"ts": reloj_iso(S), "para": f"{u['nombre']} (dueña)",
                                      "texto": f"Tu código de autorización es {codigo}. Vence en 3 minutos. No lo compartas."})
    S["whatsapp_simulado"] = S["whatsapp_simulado"][:8]
    auditar(S, _ctx(S, uid), "OTP_SOLICITADO", detalle={"canal": "whatsapp (simulado)"}, severidad="MEDIA")
    return {"enviado": True, "vence_en_s": OTP_SEGUNDOS}


def _validar_autorizacion(S, uid, pin, otp, C):
    p = S["pin"]
    if otp:
        o = S.get("otp")
        if not o or o["usuario"] != uid or ahora_epoch() > o["expira"]:
            auditar(S, C, "OTP_INVALIDO", resultado="RECHAZADO", severidad="MEDIA")
            raise ErrorCompras("El código venció o no es válido. Pide uno nuevo.", "OTP_INVALIDO", 401)
        if not hmac.compare_digest(_hash(str(otp).strip(), o["sal"]), o["hash"]):
            auditar(S, C, "OTP_INVALIDO", resultado="RECHAZADO", severidad="MEDIA")
            raise ErrorCompras("El código no coincide.", "OTP_INVALIDO", 401)
        S["otp"] = None
        p["intentos"], p["bloqueado_hasta"] = 0, 0
        return "OTP"
    if ahora_epoch() < p["bloqueado_hasta"]:
        restante = int(p["bloqueado_hasta"] - ahora_epoch())
        raise ErrorCompras(f"PIN bloqueado por {restante // 60 + 1} min. Usa el código por WhatsApp.", "PIN_BLOQUEADO", 423)
    if not str(pin or "").isdigit() or not 4 <= len(str(pin)) <= 6:
        raise ErrorCompras("El PIN tiene de 4 a 6 dígitos.", "VALIDACION", 422)
    if hmac.compare_digest(_hash(str(pin), p["sal"]), p["hash"]):
        p["intentos"] = 0
        return "PIN"
    p["intentos"] += 1
    if p["intentos"] >= MAX_INTENTOS_PIN:
        p["bloqueado_hasta"] = ahora_epoch() + BLOQUEO_SEGUNDOS
        auditar(S, C, "PIN_BLOQUEADO", resultado="RECHAZADO", severidad="ALTA", detalle={"intentos": p["intentos"]})
        notificar(S, C, "Alerta de seguridad: se bloqueó el PIN tras 3 intentos fallidos al enviar una orden de compra.")
        raise ErrorCompras("PIN incorrecto. Se bloqueó tras 3 intentos: usa el código por WhatsApp.", "PIN_BLOQUEADO", 423)
    auditar(S, C, "PIN_INVALIDO", resultado="RECHAZADO", severidad="MEDIA", detalle={"intentos": p["intentos"]})
    raise ErrorCompras(f"PIN incorrecto. Te quedan {MAX_INTENTOS_PIN - p['intentos']} intento(s).", "PIN_INVALIDO", 401)


def _marcar_enviada(S, C, oc, metodo, uid):
    prov = motor.idx(S)["prov"][oc["proveedor_id"]]
    canal = prov.get("canal_preferido", "email")
    oc["enviada_al_proveedor"] = {"ts": reloj_iso(S), "por": uid, "canal": canal, "autorizacion": metodo}
    _historial(S, oc, f"Enviada al proveedor por {'WhatsApp' if canal == 'whatsapp' else 'correo'} · autorizada con {metodo}", uid)
    auditar(S, C, "OC_ENVIADA_PROVEEDOR", recurso=oc["numero"],
            detalle={"proveedor_id": oc["proveedor_id"], "canal": canal, "monto": monto_oc(oc), "autorizacion": metodo,
                     "propuesta_agente": oc.get("propuesta_id"), "corrida_agente": oc.get("corrida_id")})
    if canal == "whatsapp":
        S["whatsapp_simulado"].insert(0, {"ts": reloj_iso(S), "para": prov["razon_social"],
                                          "texto": f"{S['tenant']['nombre_comercial']} te envía la orden {oc['numero']} (PDF). Entrega estimada {oc['fecha_entrega']}."})
        S["whatsapp_simulado"] = S["whatsapp_simulado"][:8]


def enviar_al_proveedor(S, uid, numero, pin=None, otp=None):
    return enviar_lote(S, uid, [numero], pin, otp)[0]


def enviar_lote(S, uid, numeros, pin=None, otp=None):
    """Envía una o varias órdenes Aprobadas con una sola autorización (ventana de confianza del PIN, core-base RF-38).
    Cada orden queda auditada por separado con la persona que la autorizó."""
    ordenes = [_oc(S, n) for n in numeros]
    if not ordenes:
        raise ErrorCompras("No hay órdenes para enviar.", "VALIDACION", 422)
    for oc in ordenes:
        _exigir(S, uid, "enviar", oc)
        if oc["estado"] != "APROBADA" or oc["enviada_al_proveedor"]:
            raise ErrorCompras(f"{oc['numero']}: solo se envía una orden Aprobada que aún no se envió.", "ESTADO_INVALIDO")
    C = _ctx(S, uid)
    metodo = _validar_autorizacion(S, uid, pin, otp, C)
    for oc in ordenes:
        auditar(S, C, "AUTORIZACION_" + metodo, recurso=oc["numero"], severidad="MEDIA",
                detalle={"accion": "enviar_oc_proveedor", "lote": numeros if len(numeros) > 1 else None})
        _marcar_enviada(S, C, oc, metodo, uid)
    return ordenes
