"""Motor de cálculo determinista del Agente de Abastecimiento (celda 3.2 del notebook).

El modelo nunca calcula cantidades: las pide a estas funciones a través de las herramientas.
Las unidades en tránsito salen de las órdenes reales de la demo (enviadas al proveedor y no recibidas),
así que al despachar un borrador del agente la siguiente corrida ya no vuelve a pedirlo.
"""
import hashlib
import json
import math
from collections import defaultdict
from datetime import date, timedelta

from .estado import reloj

ROL_TODO = "Administrador"   # el rol Administrador tiene todos los permisos


def idx(S):
    d = S["datos"]
    return {
        "prod": {p["sku"]: p for p in d["PRODUCTOS"]},
        "prov": {p["proveedor_id"]: p for p in d["PROVEEDORES"]},
        "alm": {a["almacen_id"]: a for a in d["ALMACENES"]},
        "suc": {s["sucursal_id"]: s for s in d["SUCURSALES"]},
        "usr": {u["usuario_id"]: u for u in d["USUARIOS"]},
        "stock": {(s["sku"], s["almacen_id"]): s for s in d["STOCK"]},
    }


def usuario(S, uid):
    return next((u for u in S["datos"]["USUARIOS"] if u["usuario_id"] == uid), None)


def tiene_permiso(S, uid, permiso) -> bool:
    u = usuario(S, uid)
    return bool(u and u.get("activo", True) and (u["rol"] == ROL_TODO or permiso in u["permisos"]))


def almacenes_visibles(S, uid) -> set:
    u = usuario(S, uid)
    if not u:
        return set()
    if not S["config"].get("restriccion_visualizacion_cruzada", True):
        return {a["almacen_id"] for a in S["datos"]["ALMACENES"]}
    return {a["almacen_id"] for a in S["datos"]["ALMACENES"] if a["sucursal_id"] in u["sucursales"]}


def hoy(S) -> date:
    return reloj(S).date()


def ventas_en_ventana(S, sku, almacen_id, dias=None) -> int:
    """Unidades vendidas en los últimos `dias` días, sin contar hoy (igual que el notebook)."""
    dias = dias or S["config"]["ventana_consumo_dias"]
    h = hoy(S)
    desde, hasta = (h - timedelta(days=dias)).isoformat(), h.isoformat()
    return sum(v["cantidad"] for v in S["datos"]["VENTAS_DIARIAS"]
               if v["sku"] == sku and v["almacen_id"] == almacen_id and desde <= v["fecha"] < hasta)


def vendidas_hoy(S, sku, almacen_id) -> int:
    h = hoy(S).isoformat()
    return sum(v["cantidad"] for v in S["datos"]["VENTAS_DIARIAS"]
               if v["sku"] == sku and v["almacen_id"] == almacen_id and v["fecha"] == h)


def unidades_en_transito(S, sku, almacen_id):
    total, ocs = 0, set()
    for o in S["ocs"]:
        if o["enviada_al_proveedor"] and o["estado"] in ("APROBADA", "RECIBIDA_PARCIAL"):
            for l in o["lineas"]:
                if l["sku"] == sku and l["almacen_id"] == almacen_id and l["cantidad"] > l["recibida"]:
                    total += l["cantidad"] - l["recibida"]
                    ocs.add(o["numero"])
    return total, sorted(ocs)


def ultima_compra(S, sku):
    compras = sorted((c for c in S["datos"]["COMPRAS_HISTORICAS"] if c["sku"] == sku), key=lambda c: c["fecha"])
    return compras[-1] if compras else None


def calcular_sugerencia(S, sku, almacen_id) -> dict:
    """Cantidad sugerida de RF-CORE-AI-06 con cada paso visible. Nunca es un EOQ."""
    cfg = S["config"]
    I = idx(S)
    fila = I["stock"][(sku, almacen_id)]
    vendidas = ventas_en_ventana(S, sku, almacen_id)
    vel_exacta = vendidas / cfg["ventana_consumo_dias"]
    repo = max(math.ceil(round(vel_exacta * cfg["dias_cobertura"] - fila["stock_disponible"], 6)), 0)
    faltante = max(fila["stock_minimo"] - fila["stock_disponible"], 0)
    necesidad = max(repo, faltante)
    transito, ocs = unidades_en_transito(S, sku, almacen_id)
    sugerida = max(necesidad - transito, 0)
    return {
        "sku": sku, "almacen_id": almacen_id, "sucursal_id": I["alm"][almacen_id]["sucursal_id"],
        "vendidas_en_ventana": vendidas, "ventana_dias": cfg["ventana_consumo_dias"],
        "velocidad_diaria": round(vel_exacta, 2), "dias_cobertura": cfg["dias_cobertura"],
        "stock_disponible": fila["stock_disponible"], "stock_minimo": fila["stock_minimo"],
        "reposicion_analytics": repo, "faltante_al_minimo": faltante, "necesidad": necesidad,
        "en_transito": transito, "oc_en_transito": ocs, "cantidad_sugerida": sugerida,
        "formula": "max(ceil(velocidad × cobertura − stock), mínimo − stock) − en tránsito, nunca negativo",
        "es_lote_economico": False,
    }


def eventos_pendientes(S) -> list:
    """Eventos no procesados dentro del alcance del agente y de la visibilidad de quien lo configuró."""
    cfg = S["config"]
    I = idx(S)
    incluidas = set(cfg["sucursales_incluidas"]) if cfg["alcance_modo"] == "ALGUNAS" else set(I["suc"])
    visibles = almacenes_visibles(S, cfg["configurado_por"])
    return [e for e in S["eventos"]
            if not e["procesado"] and e["almacen_id"] in visibles and e["almacen_id"] in I["alm"]
            and I["alm"][e["almacen_id"]]["sucursal_id"] in incluidas]


def construir_propuesta(S) -> dict:
    """Agrupa los eventos pendientes en borradores previstos. Mismo insumo → mismo propuesta_id."""
    cfg = S["config"]
    I = idx(S)
    pendientes = eventos_pendientes(S)
    por_clave = defaultdict(list)
    for e in pendientes:
        por_clave[(e["sku"], e["almacen_id"])].append(e["evento_id"])
    grupos, excluidas = defaultdict(list), []
    for (sku, alm), evs in sorted(por_clave.items()):
        prod = I["prod"][sku]
        if not prod.get("activo", True):
            excluidas.append({"sku": sku, "almacen_id": alm, "motivo": "variante inactiva", "evento_ids": evs})
            continue
        s = calcular_sugerencia(S, sku, alm)
        if s["cantidad_sugerida"] == 0:
            motivo = "cubierto por OC en tránsito" if s["en_transito"] > 0 else "stock suficiente para la cobertura"
            excluidas.append({"sku": sku, "almacen_id": alm, "motivo": motivo, "evento_ids": evs,
                              "oc_en_transito": s["oc_en_transito"]})
            continue
        compra = ultima_compra(S, sku)
        proveedor_id = compra["proveedor_id"] if compra else None
        costo = compra["costo_unitario"] if compra else None
        linea = {
            "sku": sku, "producto": f"{prod['producto']} — {prod['variante']}", "almacen_id": alm,
            "sucursal_id": s["sucursal_id"], "cantidad_sugerida": s["cantidad_sugerida"],
            "stock_disponible": s["stock_disponible"], "stock_minimo": s["stock_minimo"],
            "en_transito": s["en_transito"], "velocidad_diaria": s["velocidad_diaria"],
            "reposicion_analytics": s["reposicion_analytics"], "costo_unitario_ref": costo,
            "subtotal_ref": round(costo * s["cantidad_sugerida"], 2) if costo is not None else None,
            "evento_ids": evs, "editable": True, "detalle": s,
        }
        sucursal = s["sucursal_id"] if cfg["alcance_modo"] == "TODAS_POR_SEPARADO" else None
        grupos[(proveedor_id, sucursal)].append(linea)
    previstos = []
    for (proveedor_id, sucursal), lineas in sorted(grupos.items(), key=lambda kv: (kv[0][0] is None, kv[0][0] or "", kv[0][1] or "")):
        subtotales = [l["subtotal_ref"] for l in lineas if l["subtotal_ref"] is not None]
        previstos.append({
            "proveedor_id": proveedor_id,
            "proveedor": I["prov"][proveedor_id]["razon_social"] if proveedor_id else "Sin proveedor asignado",
            "sin_proveedor_asignado": proveedor_id is None, "sucursal_id": sucursal, "lineas": lineas,
            "total_ref": round(sum(subtotales), 2) if subtotales else None,
        })
    contenido = {"tenant": S["tenant"]["tenant_id"], "alcance": cfg["alcance_modo"], "reloj": hoy(S).isoformat(),
                 "previstos": [{k: v for k, v in p.items()} for p in previstos], "excluidas": excluidas}
    propuesta_id = "PROP-" + hashlib.sha256(json.dumps(contenido, sort_keys=True, default=str).encode()).hexdigest()[:10]
    return {"propuesta_id": propuesta_id, "alcance_modo": cfg["alcance_modo"],
            "eventos_analizados": sorted(e["evento_id"] for e in pendientes),
            "borradores_previstos": previstos, "lineas_excluidas": excluidas}


CAMPOS_COSTO = ("costo_unitario_ref", "subtotal_ref", "total_ref", "costo_unitario", "costo_referencia", "monto", "subtotal")


def ocultar_costos(S, obj, uid):
    """Quita costos y montos si el usuario no tiene 'costos.ver'."""
    if tiene_permiso(S, uid, "costos.ver"):
        return obj
    if isinstance(obj, dict):
        return {k: (None if k in CAMPOS_COSTO else ocultar_costos(S, v, uid)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [ocultar_costos(S, x, uid) for x in obj]
    return obj
