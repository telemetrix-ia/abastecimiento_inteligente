"""Herramientas del agente con guardia de seguridad (celda 3.4 del notebook).

Catálogo cerrado (S1): lo que no está en CATALOGO no existe para el agente. Cada herramienta declara
core dueño, tipo, permiso, modos permitidos y su JSON Schema para el tool use de Claude.
"""
import copy
import json
import re
import time

from . import motor
from .datos import REGLAS_AGENTE, CONDICION_PAGO
from .estado import auditar, log_tecnico, notificar, reloj_iso

CORRIDA, CONSULTA = ("programada", "a_demanda"), ("consulta",)
RE_SKU = re.compile(r"^[A-Z0-9]{2,5}(-[A-Z0-9]{1,5}){1,3}$")
RE_PROPUESTA = re.compile(r"^PROP-[0-9a-f]{10}$")

_SKU = {"type": "string", "description": "Código de la Variante, ej. COL-PER-BLA"}
_ALM = {"type": "string", "description": "ALM-01 (Huallaga) o ALM-02 (Gamarra)"}


def _schema(props=None, req=None):
    return {"type": "object", "properties": props or {}, "required": req or []}


CATALOGO = {
    "consultar_estado_agente": dict(core="core-ai", tipo="lectura", permiso="ia.chat", modos=CORRIDA + CONSULTA, schema=_schema(),
        descripcion="Estado del Agente de Abastecimiento: si está activo, hora de la corrida programada, alcance, días de cobertura, ventana de consumo, última corrida, eventos pendientes y saldo de créditos."),
    "buscar_producto": dict(core="core-product", tipo="lectura", permiso="stock.ver", modos=CORRIDA + CONSULTA,
        schema=_schema({"texto": {"type": "string", "description": "Nombre, color, talla o código"}}, ["texto"]),
        descripcion="Busca Variantes por nombre, color, talla o código (ej. 'collar perlas blanco'). Devuelve hasta 5 coincidencias con su SKU. Úsala cuando el usuario nombre un producto sin su código."),
    "consultar_cola_quiebres": dict(core="core-stock", tipo="lectura", permiso="stock.ver", modos=CORRIDA + CONSULTA, schema=_schema(),
        descripcion="Eventos de quiebre de stock pendientes que el agente procesará en su próxima corrida, solo de las sucursales visibles para el usuario."),
    "consultar_stock": dict(core="core-stock", tipo="lectura", permiso="stock.ver", modos=CORRIDA + CONSULTA,
        schema=_schema({"sku": _SKU, "almacen_id": _ALM}, ["sku"]),
        descripcion="Stock disponible y cantidad mínima de una Variante, en un almacén o en todos los que el usuario puede ver."),
    "consultar_consumo_kardex": dict(core="core-stock", tipo="lectura", permiso="stock.ver", modos=CORRIDA + CONSULTA,
        schema=_schema({"sku": _SKU, "almacen_id": _ALM}, ["sku"]),
        descripcion="Consumo por venta de una Variante según el Kardex: unidades vendidas hoy, en los últimos 7 y 30 días, y velocidad diaria."),
    "calcular_cantidad_sugerida": dict(core="core-ai", tipo="lectura", permiso="stock.ver", modos=CORRIDA + CONSULTA,
        schema=_schema({"sku": _SKU, "almacen_id": _ALM}, ["sku", "almacen_id"]),
        descripcion="Calcula la cantidad sugerida a reponer de una Variante en un almacén, con cada paso (velocidad, cobertura, mínimo, en tránsito). Úsala para '¿cuánto pido?' o '¿por qué esa cantidad?'."),
    "consultar_oc_en_transito": dict(core="core-account", tipo="lectura", permiso="compras.ver", modos=CORRIDA + CONSULTA,
        schema=_schema({"sku": _SKU}),
        descripcion="Órdenes de compra ya enviadas al proveedor y aún no recibidas, con unidades pendientes y fecha estimada. Opcionalmente filtra por SKU."),
    "consultar_ultimo_proveedor": dict(core="core-account", tipo="lectura", permiso="compras.ver", modos=CORRIDA + CONSULTA,
        schema=_schema({"sku": _SKU}, ["sku"]),
        descripcion="Proveedor de la última compra registrada de una Variante, con fecha y costo unitario."),
    "listar_borradores_agente": dict(core="core-account", tipo="lectura", permiso="compras.ver", modos=CORRIDA + CONSULTA, schema=_schema(),
        descripcion="Órdenes de compra que propuso el agente, con su estado actual (Borrador, Pendiente de aprobación, Aprobada, Enviada), líneas y totales."),
    "buscar_reglas_abastecimiento": dict(core="core-ai", tipo="lectura", permiso="ia.chat", modos=CORRIDA + CONSULTA,
        schema=_schema({"consulta": {"type": "string"}}, ["consulta"]),
        descripcion="Busca en las reglas oficiales del agente (cálculo, cuándo corre, PIN, créditos, proveedores, alcance, aprobación, auditoría). Devuelve fragmentos con su código AB-xx."),
    "generar_propuesta_abastecimiento": dict(core="core-ai", tipo="lectura", permiso="compras.borrador_ia", modos=CORRIDA, schema=_schema(),
        descripcion="Solo en CORRIDA. Analiza los eventos de quiebre pendientes y calcula la propuesta: borradores previstos por proveedor con sus líneas y cantidades, y líneas excluidas con su motivo. No crea nada. Devuelve un propuesta_id."),
    "crear_borradores_oc": dict(core="core-account", tipo="escritura", permiso="compras.borrador_ia", modos=CORRIDA,
        schema=_schema({"propuesta_id": {"type": "string", "description": "propuesta_id exacto devuelto por generar_propuesta_abastecimiento"}}, ["propuesta_id"]),
        descripcion="Solo en CORRIDA. Crea los Borradores de Orden de Compra de una propuesta ya generada, usando su propuesta_id exacto. Nunca aprueba ni envía. Si ya fue creada, devuelve los mismos borradores."),
}


class Denegado(Exception):
    pass


def herramientas_para(modo):
    """Definiciones para la API de Claude. El chat de consulta nunca recibe herramientas de escritura (S2)."""
    return [{"name": n, "description": m["descripcion"], "input_schema": m["schema"]}
            for n, m in CATALOGO.items() if modo in m["modos"]]


def _quien(S, C):
    return S["config"]["configurado_por"] if C["modo"] == "programada" else C["usuario_id"]


def _sku(v):
    v = (v or "").strip().upper()
    if not RE_SKU.match(v):
        raise ValueError("SKU con formato inválido")
    return v


def _almacen(S, C, v, obligatorio=False):
    v = (v or "").strip().upper()
    if not v:
        if obligatorio:
            raise ValueError("almacen_id es obligatorio")
        return None
    if v not in motor.idx(S)["alm"]:
        raise ValueError("almacén inexistente")
    if v not in motor.almacenes_visibles(S, _quien(S, C)):
        raise Denegado("VISIBILIDAD_CRUZADA: el usuario no tiene asignada la sucursal de ese almacén")
    return v


def ejecutar_herramienta(S, C, nombre, argumentos) -> str:
    """Guardia común (S1, S2, S5, S9): catálogo, modo, permiso, validación, auditoría y log técnico."""
    meta = CATALOGO.get(nombre)
    inicio = time.perf_counter()
    argumentos = argumentos if isinstance(argumentos, dict) else {}
    try:
        if not meta:
            raise Denegado("HERRAMIENTA_NO_AUTORIZADA")
        if C["modo"] not in meta["modos"]:
            raise Denegado(f"MODO_NO_PERMITIDO: {meta['tipo']} no disponible en modo {C['modo']}")
        if not motor.tiene_permiso(S, _quien(S, C), meta["permiso"]):
            raise Denegado(f"SIN_PERMISO: requiere {meta['permiso']}")
        extra = set(argumentos) - set(meta["schema"]["properties"])
        if extra:
            raise ValueError(f"argumentos no permitidos: {sorted(extra)}")
        if any(str(v).upper().startswith("TEN-") and str(v) != S["tenant"]["tenant_id"] for v in argumentos.values()):
            raise Denegado("TENANT_AJENO")
        resultado = motor.ocultar_costos(S, FUNCIONES[nombre](S, C, **argumentos), _quien(S, C))
        estado = "OK"
    except Denegado as exc:
        resultado, estado = {"permitido": False, "motivo": str(exc)}, "DENEGADO"
        C["denegaciones"].append(nombre)
    except (ValueError, KeyError, TypeError) as exc:
        resultado, estado = {"permitido": True, "error": "ARGUMENTO_INVALIDO", "detalle": str(exc)[:200]}, "ARGUMENTO_INVALIDO"
    auditar(S, C, "TOOL_" + nombre.upper(), resultado=estado, recurso=(meta or {}).get("core"),
            detalle={"argumentos": argumentos, "tipo": (meta or {}).get("tipo")},
            severidad="MEDIA" if estado == "DENEGADO" else "BAJA")
    log_tecnico(S, C, "tool_call", componente="core-ai", herramienta=nombre, estado=estado,
                latencia_ms=round((time.perf_counter() - inicio) * 1000, 1))
    return json.dumps(resultado, ensure_ascii=False, default=str)


# ─────────────────────────────────────────────────────────────── implementaciones
def consultar_estado_agente(S, C):
    cfg = S["config"]
    return {"agente_activo": cfg["agente_abastecimiento_activo"], "addon_multi_agente": cfg["addon_multi_agente_activo"],
            "hora_corrida_programada": cfg["hora_corrida_programada"], "zona_horaria": S["tenant"]["zona_horaria"],
            "alcance_modo": cfg["alcance_modo"], "dias_cobertura": cfg["dias_cobertura"],
            "ventana_consumo_dias": cfg["ventana_consumo_dias"], "ultima_corrida": cfg["ultima_corrida"],
            "eventos_pendientes": len(motor.eventos_pendientes(S)), "saldo_creditos": S["saldo_creditos"],
            "reserva_creditos_agentes": cfg["reserva_creditos_agentes"],
            "costo_corrida": S["costos_creditos"]["corrida_abastecimiento"], "costo_consulta": S["costos_creditos"]["consulta_chat"],
            "tope_aprobacion_soles": cfg.get("tope_aprobacion")}


def buscar_producto(S, C, texto):
    texto = (texto or "").strip().lower()
    if not 2 <= len(texto) <= 80:
        raise ValueError("texto de búsqueda de 2 a 80 caracteres")
    palabras = [p for p in re.split(r"\W+", texto) if len(p) > 2]

    def puntaje(p):
        base = f"{p['sku']} {p['producto']} {p['variante']} {p['categoria']}".lower()
        return sum(pal[:5] in base for pal in palabras)
    hallados = sorted((p for p in S["datos"]["PRODUCTOS"] if puntaje(p) > 0), key=lambda p: -puntaje(p))[:5]
    if not hallados:
        return {"encontrado": False, "busqueda": texto, "mensaje": "No hay productos que coincidan."}
    return {"encontrado": True, "coincidencias": [{"sku": p["sku"], "producto": p["producto"], "variante": p["variante"]} for p in hallados]}


def consultar_cola_quiebres(S, C):
    vis = motor.almacenes_visibles(S, _quien(S, C))
    I = motor.idx(S)
    pend = [e for e in motor.eventos_pendientes(S) if e["almacen_id"] in vis]
    return {"total": len(pend), "eventos": [{**e, "producto": I["prod"][e["sku"]]["producto"] + " — " + I["prod"][e["sku"]]["variante"]} for e in pend]}


def consultar_stock(S, C, sku, almacen_id=""):
    sku, alm = _sku(sku), _almacen(S, C, almacen_id)
    I = motor.idx(S)
    if sku not in I["prod"]:
        return {"encontrado": False, "sku": sku, "mensaje": "No existe un producto con ese código en este negocio."}
    vis = motor.almacenes_visibles(S, _quien(S, C))
    filas = [s for s in S["datos"]["STOCK"] if s["sku"] == sku and s["almacen_id"] in vis and (alm is None or s["almacen_id"] == alm)]
    return {"encontrado": True, "sku": sku, "producto": I["prod"][sku]["producto"] + " — " + I["prod"][sku]["variante"],
            "stock": [{**f, "almacen": I["alm"][f["almacen_id"]]["nombre"]} for f in filas]}


def consultar_consumo_kardex(S, C, sku, almacen_id=""):
    sku, alm = _sku(sku), _almacen(S, C, almacen_id)
    if sku not in motor.idx(S)["prod"]:
        return {"encontrado": False, "sku": sku, "mensaje": "No existe un producto con ese código en este negocio."}
    vis = motor.almacenes_visibles(S, _quien(S, C))
    salida = []
    for s in S["datos"]["STOCK"]:
        if s["sku"] == sku and s["almacen_id"] in vis and (alm is None or s["almacen_id"] == alm):
            v30 = motor.ventas_en_ventana(S, sku, s["almacen_id"], 30)
            salida.append({"almacen_id": s["almacen_id"], "vendidas_hoy": motor.vendidas_hoy(S, sku, s["almacen_id"]),
                           "vendidas_7d": motor.ventas_en_ventana(S, sku, s["almacen_id"], 7), "vendidas_30d": v30,
                           "velocidad_diaria_30d": round(v30 / 30, 2)})
    return {"encontrado": True, "sku": sku, "consumo": salida}


def calcular_cantidad_sugerida(S, C, sku, almacen_id):
    sku, alm = _sku(sku), _almacen(S, C, almacen_id, obligatorio=True)
    if (sku, alm) not in motor.idx(S)["stock"]:
        return {"encontrado": False, "sku": sku, "almacen_id": alm, "mensaje": "Esa Variante no tiene stock registrado en ese almacén."}
    return {"encontrado": True, **motor.calcular_sugerencia(S, sku, alm)}


def consultar_oc_en_transito(S, C, sku=""):
    sku = _sku(sku) if sku else None
    vis = motor.almacenes_visibles(S, _quien(S, C))
    I = motor.idx(S)
    filas = []
    for o in S["ocs"]:
        if o["enviada_al_proveedor"] and o["estado"] in ("APROBADA", "RECIBIDA_PARCIAL"):
            for l in o["lineas"]:
                if l["almacen_id"] in vis and (sku is None or l["sku"] == sku) and l["cantidad"] > l["recibida"]:
                    filas.append({"oc": o["numero"], "proveedor": I["prov"][o["proveedor_id"]]["razon_social"],
                                  "sku": l["sku"], "almacen_id": l["almacen_id"], "pendiente": l["cantidad"] - l["recibida"],
                                  "fecha_estimada": o["fecha_entrega"]})
    return {"total_lineas": len(filas), "lineas": filas}


def consultar_ultimo_proveedor(S, C, sku):
    sku = _sku(sku)
    I = motor.idx(S)
    if sku not in I["prod"]:
        return {"encontrado": False, "sku": sku, "mensaje": "No existe un producto con ese código en este negocio."}
    c = motor.ultima_compra(S, sku)
    if not c:
        return {"encontrado": True, "sku": sku, "proveedor_id": None, "mensaje": "Sin compras previas: va a un borrador sin proveedor asignado."}
    return {"encontrado": True, "sku": sku, "proveedor_id": c["proveedor_id"], "proveedor": I["prov"][c["proveedor_id"]]["razon_social"],
            "fecha": c["fecha"], "costo_unitario": c["costo_unitario"]}


def listar_borradores_agente(S, C):
    vis = motor.almacenes_visibles(S, _quien(S, C))
    propias = [o for o in S["ocs"] if o["origen"] == "AGENTE" and all(l["almacen_id"] in vis for l in o["lineas"])]
    return {"total": len(propias), "ordenes": [resumen_oc(S, o) for o in propias]}


def buscar_reglas_abastecimiento(S, C, consulta):
    consulta = (consulta or "").strip().lower()
    if not 3 <= len(consulta) <= 200:
        raise ValueError("consulta de 3 a 200 caracteres")
    palabras = {p[:6] for p in re.split(r"\W+", consulta) if len(p) > 3}
    puntuadas = sorted(REGLAS_AGENTE, key=lambda r: -sum(p in (r["titulo"] + " " + r["texto"]).lower() for p in palabras))
    return {"fragmentos": [f"{r['id']} · {r['titulo']}: {r['texto']}" for r in puntuadas[:3]]}


def generar_propuesta_abastecimiento(S, C):
    propuesta = motor.construir_propuesta(S)
    S["propuestas"] = {k: v for k, v in S["propuestas"].items() if k in S["idempotencia"]}   # no acumular propuestas huérfanas
    S["propuestas"][propuesta["propuesta_id"]] = {**propuesta, "corrida_id": C["corrida_id"]}
    C["propuesta_id"] = propuesta["propuesta_id"]
    C["lineas_excluidas"] = propuesta["lineas_excluidas"]
    resumen = copy.deepcopy(propuesta)
    for b in resumen["borradores_previstos"]:
        for l in b["lineas"]:
            l.pop("detalle", None)
    return resumen


def crear_borradores_oc(S, C, propuesta_id):
    propuesta_id = (propuesta_id or "").strip()
    if not RE_PROPUESTA.match(propuesta_id):
        raise ValueError("propuesta_id con formato inválido")
    propuesta = S["propuestas"].get(propuesta_id)
    if not propuesta or propuesta["corrida_id"] != C["corrida_id"]:
        raise Denegado("PROPUESTA_DESCONOCIDA: solo se aceptan propuestas generadas en esta corrida")
    if propuesta_id in S["idempotencia"]:
        ids = S["idempotencia"][propuesta_id]
        C["borradores_creados"] = [o for o in S["ocs"] if o["numero"] in ids]
        return {"duplicado": True, "oc_ids": ids}
    creadas = []
    ts = reloj_iso(S)
    for p in propuesta["borradores_previstos"]:
        S["contador_oc"] += 1
        oc = {"numero": f"OC-{S['contador_oc']:04d}", "proveedor_id": p["proveedor_id"], "estado": "BORRADOR",
              "origen": "AGENTE", "corrida_id": C["corrida_id"], "propuesta_id": propuesta_id,
              "creada_por": "agente:abastecimiento", "creada_en": ts, "fecha_entrega": None,
              "condicion_pago": CONDICION_PAGO.get(p["proveedor_id"], "Contado") if p["proveedor_id"] else None,
              "sin_proveedor_asignado": p["sin_proveedor_asignado"], "sucursal_id": p["sucursal_id"],
              "lineas": [{"sku": l["sku"], "almacen_id": l["almacen_id"], "sucursal_id": l["sucursal_id"],
                          "cantidad": l["cantidad_sugerida"], "recibida": 0, "costo_unitario": l["costo_unitario_ref"],
                          "sugerida": l["cantidad_sugerida"], "detalle_sugerencia": l["detalle"], "evento_ids": l["evento_ids"]}
                         for l in p["lineas"]],
              "enviada_al_proveedor": None,
              "historial": [{"ts": ts, "accion": f"Propuesta por el agente · corrida {C['corrida_id']}", "actor": "agente:abastecimiento"}]}
        S["ocs"].append(oc)
        creadas.append(oc)
        auditar(S, C, "CREAR_BORRADOR_OC", recurso=oc["numero"], actor_tipo="AGENTE", actor_id="agente:abastecimiento",
                detalle={"proveedor_id": oc["proveedor_id"], "lineas": len(oc["lineas"]), "total_ref": monto_oc(oc), "propuesta_id": propuesta_id})
    procesados = {ev for p in propuesta["borradores_previstos"] for l in p["lineas"] for ev in l["evento_ids"]}
    procesados |= {ev for x in propuesta["lineas_excluidas"] for ev in x["evento_ids"]}
    for e in S["eventos"]:
        if e["evento_id"] in procesados:
            e["procesado"] = True
    S["idempotencia"][propuesta_id] = [o["numero"] for o in creadas]
    C["borradores_creados"] = creadas
    if creadas:
        notificar(S, C, f"El Agente de Abastecimiento dejó {len(creadas)} borrador(es) de OC para tu revisión: "
                  + ", ".join(o["numero"] for o in creadas) + ". Enviarlas al proveedor exige tu PIN.", enlace="#/compras?origen=IA")
    return {"duplicado": False, "oc_ids": [o["numero"] for o in creadas], "eventos_marcados_procesados": sorted(procesados)}


FUNCIONES = {n: globals()[n] for n in CATALOGO}


# ─────────────────────────────────────────────────────────────── utilidades de órdenes
def monto_oc(oc):
    costos = [l["costo_unitario"] * l["cantidad"] for l in oc["lineas"] if l["costo_unitario"] is not None]
    return round(sum(costos), 2) if costos else None


def resumen_oc(S, oc):
    I = motor.idx(S)
    estado = oc["estado"]
    return {"numero": oc["numero"], "estado": estado, "enviada_al_proveedor": bool(oc["enviada_al_proveedor"]),
            "proveedor": I["prov"][oc["proveedor_id"]]["razon_social"] if oc["proveedor_id"] else "Sin proveedor asignado",
            "lineas": [{"sku": l["sku"], "almacen_id": l["almacen_id"], "cantidad": l["cantidad"], "sugerida": l["sugerida"]} for l in oc["lineas"]],
            "monto": monto_oc(oc), "creada_en": oc["creada_en"]}
