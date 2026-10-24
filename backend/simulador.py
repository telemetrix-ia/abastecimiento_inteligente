"""Panel de demo: simula ventas (como haría el POS), publica quiebres (como haría core-stock),
adelanta el reloj, dispara la corrida de las 21:00 y la llegada del proveedor.

Nada de esto es parte del ERP: existe para conducir la demostración.
"""
import math
import random
from datetime import timedelta

from . import compras, motor
from .estado import auditar, avanzar_reloj, notificar, nuevo_contexto, reloj, reloj_iso

FACTOR_DIA = {0: 0.8, 1: 0.8, 2: 0.9, 3: 0.9, 4: 1.1, 5: 1.6, 6: 1.3}
HORA_APERTURA, HORA_CIERRE = 10, 20


def _poisson(rng, lam):
    if lam <= 0:
        return 0
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


def _ctx_sistema(S, uid):
    C = nuevo_contexto(S, "consulta", uid)
    C.update({"modo": "simulador", "canal": "panel-demo", "actor_tipo": "SISTEMA", "actor_id": "core-stock (simulado)"})
    return C


def simular_ventas(S, uid, horas: int, intensidad: float = 1.0):
    """Avanza el reloj hora por hora. En horario de tienda genera ventas según la velocidad histórica,
    descuenta stock y publica un evento de quiebre cuando un producto cruza su mínimo."""
    horas = max(1, min(int(horas), 72))
    intensidad = max(0.5, min(float(intensidad), 3.0))
    C = _ctx_sistema(S, uid)
    I = motor.idx(S)
    unidades, monto, nuevos = 0, 0.0, []
    for _ in range(horas):
        momento = reloj(S)
        if HORA_APERTURA <= momento.hour < HORA_CIERRE:
            fecha = momento.date().isoformat()
            rng = random.Random(f"{S['simulacion_semilla']}|{momento.isoformat()}")
            for fila in S["datos"]["STOCK"]:
                sku, alm = fila["sku"], fila["almacen_id"]
                if fila["stock_disponible"] <= 0 or not I["prod"][sku].get("activo", True):
                    continue
                vel = motor.ventas_en_ventana(S, sku, alm, 30) / 30
                lam = vel / (HORA_CIERRE - HORA_APERTURA) * FACTOR_DIA[momento.weekday()] * intensidad
                cantidad = min(_poisson(rng, lam), fila["stock_disponible"])
                if cantidad <= 0:
                    continue
                antes = fila["stock_disponible"]
                fila["stock_disponible"] -= cantidad
                unidades += cantidad
                monto += cantidad * I["prod"][sku]["precio_venta"]
                registro = next((v for v in reversed(S["datos"]["VENTAS_DIARIAS"])
                                 if v["fecha"] == fecha and v["sku"] == sku and v["almacen_id"] == alm), None)
                if registro:
                    registro["cantidad"] += cantidad
                else:
                    S["datos"]["VENTAS_DIARIAS"].append({"fecha": fecha, "sku": sku, "almacen_id": alm, "cantidad": cantidad})
                ya_en_cola = any(not e["procesado"] and e["sku"] == sku and e["almacen_id"] == alm for e in S["eventos"])
                if antes > fila["stock_minimo"] >= fila["stock_disponible"] and not ya_en_cola:
                    numero = max([int(e["evento_id"].split("-")[1]) for e in S["eventos"]] + [1000]) + 1
                    minuto = rng.randint(0, 59)
                    evento = {"evento_id": f"EVT-{numero}", "fecha_hora": momento.replace(minute=minuto).isoformat(timespec="seconds"),
                              "sku": sku, "almacen_id": alm, "tipo": "QUIEBRE_MINIMO", "procesado": False}
                    S["eventos"].append(evento)
                    nuevos.append(evento)
                    auditar(S, C, "EVENTO_QUIEBRE_PUBLICADO", recurso=evento["evento_id"],
                            detalle={"sku": sku, "almacen_id": alm, "stock": fila["stock_disponible"], "minimo": fila["stock_minimo"]})
        avanzar_reloj(S, 1)
    S.setdefault("ciclo", {"vueltas": 0, "ultima_llegada": None, "unidades_vendidas": 0})
    S["ciclo"]["unidades_vendidas"] = S["ciclo"].get("unidades_vendidas", 0) + unidades
    if nuevos:
        notificar(S, C, f"{len(nuevos)} producto(s) cruzaron su stock mínimo. El agente los tendrá en cuenta en su próxima corrida.",
                  enlace="#/stock")
    auditar(S, C, "SIMULACION_VENTAS", detalle={"horas": horas, "unidades": unidades, "monto": round(monto, 2), "quiebres": len(nuevos)})
    return {"horas": horas, "unidades": unidades, "monto": round(monto, 2),
            "nuevos_quiebres": [{**e, "producto": I["prod"][e["sku"]]["producto"] + " — " + I["prod"][e["sku"]]["variante"]} for e in nuevos],
            "reloj": reloj_iso(S)}


def ir_a_corrida(S):
    """Lleva el reloj a la hora de la corrida programada (hoy, o mañana si ya pasó)."""
    hh, mm = [int(x) for x in S["config"]["hora_corrida_programada"].split(":")]
    ahora = reloj(S)
    objetivo = ahora.replace(hour=hh, minute=mm, second=0)
    if objetivo <= ahora:
        objetivo += timedelta(days=1)
    S["reloj"] = objetivo.replace(tzinfo=None).isoformat(timespec="seconds")


def simular_llegada(S, uid, numero):
    """Simula que el proveedor entregó todo lo pendiente: suma stock y cierra la orden (W-PURCHASE-04 está fuera de la demo)."""
    oc = next((o for o in S["ocs"] if o["numero"] == numero), None)
    if not oc or not oc["enviada_al_proveedor"] or oc["estado"] not in ("APROBADA", "RECIBIDA_PARCIAL"):
        raise ValueError("Solo llega mercadería de una orden enviada al proveedor y no recibida.")
    C = _ctx_sistema(S, uid)
    I = motor.idx(S)
    for l in oc["lineas"]:
        pendiente = l["cantidad"] - l["recibida"]
        if pendiente > 0:
            I["stock"][(l["sku"], l["almacen_id"])]["stock_disponible"] += pendiente
            l["recibida"] = l["cantidad"]
            S["datos"]["COMPRAS_HISTORICAS"].append({"compra_id": "CMP-" + numero.split("-")[1], "fecha": reloj(S).date().isoformat(),
                                                     "proveedor_id": oc["proveedor_id"], "sku": l["sku"], "cantidad": pendiente,
                                                     "costo_unitario": l["costo_unitario"]})
    oc["estado"] = "RECIBIDA"
    oc["historial"].append({"ts": reloj_iso(S), "accion": "Recibida completa (simulada)", "actor": uid})
    auditar(S, C, "RECEPCION_SIMULADA", recurso=numero)
    return oc


CONFIG_EDITABLE = {
    "addon_multi_agente_activo": bool, "agente_abastecimiento_activo": bool, "restriccion_visualizacion_cruzada": bool,
    "tope_aprobacion": float, "alcance_modo": str, "dias_cobertura": int, "hora_corrida_programada": str, "modo_ia": str,
}


def cambiar_config(S, uid, campo, valor):
    if campo == "saldo_creditos":
        S["saldo_creditos"] = max(0, min(int(valor), 100000))
    elif campo in CONFIG_EDITABLE:
        tipo = CONFIG_EDITABLE[campo]
        valor = tipo(valor) if tipo is not bool else bool(valor)
        if campo == "alcance_modo" and valor not in ("TODAS_CONSOLIDADO", "TODAS_POR_SEPARADO", "ALGUNAS"):
            raise ValueError("alcance inválido")
        if campo == "modo_ia" and valor not in ("auto", "simulado"):
            raise ValueError("modo de IA inválido")
        if campo == "dias_cobertura" and not 1 <= valor <= 90:
            raise ValueError("cobertura entre 1 y 90 días")
        if campo == "hora_corrida_programada" and not (len(valor) == 5 and valor[2] == ":" and 0 <= int(valor[:2]) <= 23):
            raise ValueError("hora HH:MM")
        S["config"][campo] = valor
    else:
        raise ValueError("Campo no editable")
    auditar(S, _ctx_sistema(S, uid), "CONFIG_CAMBIADA", detalle={"campo": campo, "valor": valor},
            actor_tipo="USUARIO", actor_id=uid)


def simular_llegada_todas(S, uid):
    """Llega todo lo enviado al proveedor y no recibido. Devuelve el stock antes y después por línea."""
    I = motor.idx(S)
    lineas, recibidas_agente = [], 0
    for oc in [o for o in S["ocs"] if o["enviada_al_proveedor"] and o["estado"] in ("APROBADA", "RECIBIDA_PARCIAL")]:
        antes = {(l["sku"], l["almacen_id"]): I["stock"][(l["sku"], l["almacen_id"])]["stock_disponible"] for l in oc["lineas"]}
        simular_llegada(S, uid, oc["numero"])
        recibidas_agente += oc["origen"] == "AGENTE"
        for l in oc["lineas"]:
            fila = I["stock"][(l["sku"], l["almacen_id"])]
            p = I["prod"][l["sku"]]
            lineas.append({"numero": oc["numero"], "origen": oc["origen"], "sku": l["sku"], "producto": f"{p['producto']} — {p['variante']}",
                           "almacen": I["alm"][l["almacen_id"]]["nombre"], "antes": antes[(l["sku"], l["almacen_id"])],
                           "despues": fila["stock_disponible"], "minimo": fila["stock_minimo"]})
    S.setdefault("ciclo", {"vueltas": 0, "ultima_llegada": None, "unidades_vendidas": 0})
    if recibidas_agente:
        S["ciclo"]["vueltas"] += 1
    S["ciclo"]["ultima_llegada"] = {"ts": reloj_iso(S), "lineas": lineas, "vuelta": S["ciclo"]["vueltas"]}
    if lineas:
        notificar(S, _ctx_sistema(S, uid), f"Llegó la mercadería de {len({l['numero'] for l in lineas})} orden(es): el stock está repuesto "
                  "y la tienda puede vender de nuevo.", enlace="#/ciclo")
    return {"lineas": lineas, "vueltas": S["ciclo"]["vueltas"], "ordenes": sorted({l["numero"] for l in lineas})}


def atajo_aprobar_agente(S, uid):
    """Atajo de demo: completa el proveedor del borrador sin proveedor (el más frecuente de su categoría, al costo de
    referencia), envía a aprobación los borradores del agente y aprueba los que quedaron pendientes por el tope."""
    I = motor.idx(S)
    resumen = {"proveedor_asignado": [], "aprobadas": [], "pendientes_tope": []}
    for oc in [o for o in S["ocs"] if o["origen"] == "AGENTE" and o["estado"] == "BORRADOR"]:
        if oc["sin_proveedor_asignado"] or not oc["proveedor_id"]:
            categoria = I["prod"][oc["lineas"][0]["sku"]]["categoria"]
            frecuencia = {}
            for c in S["datos"]["COMPRAS_HISTORICAS"]:
                if I["prod"].get(c["sku"], {}).get("categoria") == categoria:
                    frecuencia[c["proveedor_id"]] = frecuencia.get(c["proveedor_id"], 0) + 1
            proveedor = max(frecuencia, key=frecuencia.get) if frecuencia else S["datos"]["PROVEEDORES"][0]["proveedor_id"]
            for l in oc["lineas"]:
                if l["costo_unitario"] is None:
                    compras.editar_linea(S, uid, oc["numero"], l["sku"], l["almacen_id"], costo_unitario=I["prod"][l["sku"]]["costo_referencia"])
            compras.asignar_proveedor(S, uid, oc["numero"], proveedor)
            resumen["proveedor_asignado"].append({"numero": oc["numero"], "proveedor": I["prov"][proveedor]["razon_social"]})
    borradores = [o["numero"] for o in S["ocs"] if o["origen"] == "AGENTE" and o["estado"] == "BORRADOR"]
    if borradores:
        r = compras.enviar_a_aprobacion(S, uid, borradores)
        resumen["aprobadas"] += [x["numero"] for x in r["aprobadas"]]
        resumen["pendientes_tope"] = [x["numero"] for x in r["pendientes"]]
    pendientes = [o["numero"] for o in S["ocs"] if o["origen"] == "AGENTE" and o["estado"] == "PENDIENTE_APROBACION"]
    if pendientes:
        resumen["aprobadas"] += compras.aprobar(S, uid, pendientes)["aprobadas"]
    return resumen
