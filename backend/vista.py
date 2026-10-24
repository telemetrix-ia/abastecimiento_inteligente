"""Lo que ve el front: un resumen del estado filtrado por el usuario activo (permisos, sucursales y costos)."""
import os
from datetime import date

from . import motor
from .compras import acciones_posibles
from .estado import ALMACEN, reloj, reloj_iso, verificar_cadena
from .herramientas import monto_oc
from .llm import ia_real_disponible, nombre_modelo

ETIQUETA_ESTADO = {"BORRADOR": "Borrador", "PENDIENTE_APROBACION": "Pendiente de aprobación", "APROBADA": "Aprobada",
                   "RECIBIDA_PARCIAL": "Recibida en parte", "RECIBIDA": "Recibida", "ANULADA": "Anulada"}


def _nombre_actor(S, actor):
    if str(actor).startswith("agente"):
        return "Agente de Abastecimiento"
    u = motor.usuario(S, actor)
    return u["nombre"] if u else actor


def oc_resumen(S, uid, oc):
    I = motor.idx(S)
    puede_costos = motor.tiene_permiso(S, uid, "costos.ver")
    hoy = reloj(S).date()
    atraso = None
    if oc["fecha_entrega"] and oc["enviada_al_proveedor"] and oc["estado"] in ("APROBADA", "RECIBIDA_PARCIAL"):
        dias = (hoy - date.fromisoformat(oc["fecha_entrega"])).days
        atraso = dias if dias > 0 else None
    pendiente = sum(l["cantidad"] - l["recibida"] for l in oc["lineas"])
    return {
        "numero": oc["numero"], "estado": oc["estado"], "estado_etiqueta": ETIQUETA_ESTADO[oc["estado"]],
        "origen": oc["origen"], "corrida_id": oc["corrida_id"],
        "proveedor": I["prov"][oc["proveedor_id"]]["razon_social"] if oc["proveedor_id"] else None,
        "proveedor_id": oc["proveedor_id"], "condicion_pago": oc["condicion_pago"],
        "sin_proveedor_asignado": oc["sin_proveedor_asignado"],
        "creada_en": oc["creada_en"], "creada_por": _nombre_actor(S, oc["creada_por"]), "creada_por_id": oc["creada_por"],
        "fecha_entrega": oc["fecha_entrega"], "atraso_dias": atraso,
        "monto": monto_oc(oc) if puede_costos else None,
        "monto_estimado": any(l["costo_unitario"] is None for l in oc["lineas"]),
        "n_lineas": len(oc["lineas"]), "unidades": sum(l["cantidad"] for l in oc["lineas"]),
        "por_recibir": pendiente if oc["estado"] in ("APROBADA", "RECIBIDA_PARCIAL") else None,
        "recibidas": sum(l["recibida"] for l in oc["lineas"]),
        "enviada_al_proveedor": oc["enviada_al_proveedor"],
        "acciones": acciones_posibles(S, uid, oc),
    }


def oc_detalle(S, uid, oc):
    I = motor.idx(S)
    puede_costos = motor.tiene_permiso(S, uid, "costos.ver")
    r = oc_resumen(S, uid, oc)
    r["lineas"] = []
    for l in oc["lineas"]:
        p = I["prod"][l["sku"]]
        actual = I["stock"].get((l["sku"], l["almacen_id"]), {})
        r["lineas"].append({
            "sku": l["sku"], "producto": p["producto"], "variante": p["variante"], "almacen_id": l["almacen_id"],
            "almacen": I["alm"][l["almacen_id"]]["nombre"], "cantidad": l["cantidad"], "recibida": l["recibida"],
            "sugerida": l["sugerida"], "costo_unitario": l["costo_unitario"] if puede_costos else None,
            "subtotal": round(l["costo_unitario"] * l["cantidad"], 2) if (puede_costos and l["costo_unitario"] is not None) else None,
            "detalle": l["detalle_sugerencia"], "stock_actual": actual.get("stock_disponible"), "evento_ids": l["evento_ids"],
        })
    r["historial"] = [{**h, "actor_nombre": _nombre_actor(S, h["actor"])} for h in oc["historial"]]
    r["proveedores"] = [{"id": p["proveedor_id"], "nombre": p["razon_social"]} for p in S["datos"]["PROVEEDORES"] if p.get("activo", True)]
    r["puede_ver_costos"] = puede_costos
    r["tope_aprobacion"] = S["config"].get("tope_aprobacion")
    return r


ACCIONES_CICLO = {"EVENTO_QUIEBRE_PUBLICADO": "quiebre", "CREAR_BORRADOR_OC": "propuesta", "OC_APROBAR": "aprobacion",
                  "OC_ENVIAR_A_APROBACION": "aprobacion", "OC_ENVIADA_PROVEEDOR": "envio", "RECEPCION_SIMULADA": "llegada",
                  "SIMULACION_VENTAS": "venta"}


def resumen_ciclo(S, cola):
    agente = [o for o in S["ocs"] if o["origen"] == "AGENTE"]
    por_revisar = [o["numero"] for o in agente if o["estado"] in ("BORRADOR", "PENDIENTE_APROBACION")]
    por_enviar = [o["numero"] for o in agente if o["estado"] == "APROBADA" and not o["enviada_al_proveedor"]]
    en_camino = [o["numero"] for o in agente if o["enviada_al_proveedor"] and o["estado"] in ("APROBADA", "RECIBIDA_PARCIAL")]
    if por_enviar:
        etapa = "enviar"
    elif por_revisar:
        etapa = "aprobar"
    elif en_camino:
        etapa = "llegada"
    elif cola:
        etapa = "agente"
    else:
        etapa = "vender"
    eventos = []
    for a in reversed(S["auditoria"]):
        tipo = ACCIONES_CICLO.get(a["accion"])
        if tipo and not (a["accion"] == "OC_ENVIAR_A_APROBACION" and a["detalle"].get("estado") != "APROBADA"):
            eventos.append({"ts": a["ts"], "tipo": tipo, "accion": a["accion"], "recurso": a["recurso"], "actor": a["actor_id"],
                            "detalle": {k: v for k, v in a["detalle"].items() if k in ("sku", "unidades", "quiebres", "horas", "monto", "estado")}})
        if len(eventos) >= 14:
            break
    c = S.get("ciclo", {})
    return {"etapa": etapa, "cola": len(cola), "por_revisar": por_revisar, "por_enviar": por_enviar, "en_camino": en_camino,
            "recibidas": [o["numero"] for o in agente if o["estado"] == "RECIBIDA"], "vueltas": c.get("vueltas", 0),
            "unidades_vendidas": c.get("unidades_vendidas", 0), "ultima_llegada": c.get("ultima_llegada"), "eventos": eventos,
            "en_quiebre": sum(1 for f in S["datos"]["STOCK"] if f["stock_disponible"] <= f["stock_minimo"])}


def instantanea(S) -> dict:
    uid = S["usuario_activo"]
    u = motor.usuario(S, uid) or {}
    I = motor.idx(S)
    vis = motor.almacenes_visibles(S, uid)
    puede = {p: motor.tiene_permiso(S, uid, p) for p in
             ("ia.chat", "stock.ver", "compras.ver", "compras.editar", "compras.aprobar", "compras.despachar", "compras.borrador_ia", "costos.ver")}
    cfg = S["config"]

    stock = []
    if puede["stock.ver"]:
        for f in S["datos"]["STOCK"]:
            if f["almacen_id"] not in vis:
                continue
            transito, _ = motor.unidades_en_transito(S, f["sku"], f["almacen_id"])
            p = I["prod"][f["sku"]]
            estado = "quiebre" if f["stock_disponible"] <= f["stock_minimo"] else ("bajo" if f["stock_disponible"] <= f["stock_minimo"] * 1.3 else "ok")
            stock.append({"sku": f["sku"], "producto": p["producto"], "variante": p["variante"], "categoria": p["categoria"],
                          "almacen_id": f["almacen_id"], "almacen": I["alm"][f["almacen_id"]]["nombre"],
                          "stock": f["stock_disponible"], "minimo": f["stock_minimo"], "en_transito": transito,
                          "vendidas_hoy": motor.vendidas_hoy(S, f["sku"], f["almacen_id"]),
                          "vendidas_7d": motor.ventas_en_ventana(S, f["sku"], f["almacen_id"], 7), "estado": estado})

    cola = [{**e, "producto": I["prod"][e["sku"]]["producto"] + " — " + I["prod"][e["sku"]]["variante"],
             "almacen": I["alm"][e["almacen_id"]]["nombre"]}
            for e in motor.eventos_pendientes(S) if e["almacen_id"] in vis] if puede["stock.ver"] else []

    ocs = []
    if puede["compras.ver"]:
        ocs = [oc_resumen(S, uid, o) for o in sorted(S["ocs"], key=lambda o: o["numero"], reverse=True)
               if all(l["almacen_id"] in vis for l in o["lineas"])]
    mes = reloj(S).strftime("%Y-%m")
    kpis = {
        "por_aprobar": {"n": sum(o["estado"] == "PENDIENTE_APROBACION" for o in ocs),
                        "monto": round(sum(o["monto"] or 0 for o in ocs if o["estado"] == "PENDIENTE_APROBACION"), 2) if puede["costos.ver"] else None},
        "por_recibir": {"n": sum(bool(o["por_recibir"]) and bool(o["enviada_al_proveedor"]) for o in ocs),
                        "atrasadas": sum(bool(o["atraso_dias"]) for o in ocs)},
        "por_enviar": {"n": sum(o["estado"] == "APROBADA" and not o["enviada_al_proveedor"] for o in ocs)},
        "generadas_ia": {"n": sum(o["origen"] == "AGENTE" and o["estado"] in ("BORRADOR", "PENDIENTE_APROBACION") for o in ocs),
                         "borradores": sum(o["origen"] == "AGENTE" and o["estado"] == "BORRADOR" for o in ocs)},
        "compras_mes": {"monto": round(sum(o["monto"] or 0 for o in ocs if o["enviada_al_proveedor"] and (o["enviada_al_proveedor"]["ts"] or "")[:7] == mes), 2) if puede["costos.ver"] else None,
                        "n": sum(1 for o in ocs if o["enviada_al_proveedor"] and (o["enviada_al_proveedor"]["ts"] or "")[:7] == mes)},
    }
    bandeja = [o for o in ocs if o["origen"] == "AGENTE" and o["estado"] in ("BORRADOR", "PENDIENTE_APROBACION")
               or (o["origen"] == "AGENTE" and o["estado"] == "APROBADA" and not o["enviada_al_proveedor"])]
    sucursales = [I["suc"][s]["nombre"] for s in u.get("sucursales", []) if s in I["suc"]]
    auditoria = S["auditoria"]
    return {
        "meta": {"modo_ia": "openrouter" if (cfg.get("modo_ia", "auto") != "simulado" and ia_real_disponible()) else "simulado",
                 "ia_configurada": ia_real_disponible(), "modelo": nombre_modelo(),
                 "almacen": ALMACEN.nombre, "origen_datos": S["origen_datos"],
                 "pin_demo": os.environ.get("DEMO_PIN", "1234") if os.environ.get("MOSTRAR_PIN_DEMO", "1") == "1" else None},
        "reloj": reloj_iso(S),
        "tenant": {"nombre": S["tenant"]["nombre_comercial"], "razon_social": S["tenant"]["razon_social"], "plan": S["tenant"]["plan"]},
        "usuario": {"id": uid, "nombre": u.get("nombre"), "rol": u.get("rol"), "sucursales": sucursales, "puede": puede},
        "usuarios": [{"id": x["usuario_id"], "nombre": x["nombre"], "rol": x["rol"]} for x in S["datos"]["USUARIOS"]],
        "sucursales": [{"id": s["sucursal_id"], "nombre": s["nombre"]} for s in S["datos"]["SUCURSALES"]],
        "config": {k: cfg.get(k) for k in ("addon_multi_agente_activo", "agente_abastecimiento_activo", "alcance_modo", "dias_cobertura",
                                           "ventana_consumo_dias", "hora_corrida_programada", "ultima_corrida", "tope_aprobacion",
                                           "reserva_creditos_agentes", "restriccion_visualizacion_cruzada", "modo_ia")},
        "creditos": {"saldo": S["saldo_creditos"], "reserva": cfg["reserva_creditos_agentes"], "costos": S["costos_creditos"],
                     "inicial": cfg["saldo_creditos"]},
        "pin": {"bloqueado": S["pin"]["bloqueado_hasta"] > 0 and S["pin"]["intentos"] >= 3, "intentos": S["pin"]["intentos"]},
        "whatsapp": S["whatsapp_simulado"][:6],
        "notificaciones": S["notificaciones"][:12],
        "stock": stock, "cola": cola, "ocs": ocs, "kpis": kpis, "bandeja": bandeja,
        "chat": S["chat"].get(uid, []),
        "ultima_salida": S.get("ultima_salida"),
        "auditoria": {"registros": len(auditoria), "integra": verificar_cadena(auditoria)},
        "ciclo": resumen_ciclo(S, cola),
    }


def auditoria(S, limite=150):
    regs = S["auditoria"][-limite:]
    return {"integra": verificar_cadena(S["auditoria"]), "total": len(S["auditoria"]),
            "registros": [{k: r[k] for k in ("audit_id", "ts", "actor_tipo", "actor_id", "en_nombre_de", "canal", "accion",
                                             "recurso", "resultado", "severidad", "corrida_id", "detalle", "hash", "prev_hash")}
                          for r in reversed(regs)],
            "log_tecnico": S["log_tecnico"][-60:][::-1]}
