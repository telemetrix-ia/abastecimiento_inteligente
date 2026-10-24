"""Router HTTP sin dependencias. Lo usan api/index.py (Vercel) y dev_server.py (local).

Cada sesión de demo se identifica con la cabecera X-Demo-Id (la genera el navegador). Si se define
DEMO_CODIGO_ACCESO, además se exige X-Demo-Codigo para no exponer la clave de Anthropic a cualquiera.
"""
import base64
import hmac
import json
import os
import re
import time
import traceback

from . import agente, compras, datos, pruebas, simulador, vista
from .estado import ALMACEN, cargar, estado_inicial, guardar, log_tecnico, reloj_iso

MAX_CUERPO = 4 * 1024 * 1024
LIMITE_IA_POR_MINUTO = int(os.environ.get("LIMITE_IA_POR_MINUTO", "15"))
CABECERAS = {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store",
             "X-Content-Type-Options": "nosniff", "Referrer-Policy": "same-origin"}


class ErrorHTTP(Exception):
    def __init__(self, status, mensaje, codigo="ERROR"):
        super().__init__(mensaje)
        self.status, self.codigo = status, codigo


def _json(status, cuerpo):
    return status, dict(CABECERAS), json.dumps(cuerpo, ensure_ascii=False, default=str).encode()


def _limite_ia(S):
    ahora = time.time()
    S["rate_ia"] = [t for t in S.get("rate_ia", []) if ahora - t < 60]
    if len(S["rate_ia"]) >= LIMITE_IA_POR_MINUTO:
        raise ErrorHTTP(429, "Demasiadas solicitudes a la IA en un minuto. Espera unos segundos.", "RATE_LIMIT")
    S["rate_ia"].append(ahora)


def _respuesta_ia(S, salida, mensaje_usuario=None):
    uid = S["usuario_activo"]
    S["ultima_salida"] = salida
    if mensaje_usuario is not None:
        hist = S["chat"].setdefault(uid, [])
        hist.append({"rol": "user", "texto": mensaje_usuario if "PIN_ENMASCARADO" not in salida["alertas_seguridad"]
                     else agente.revisar_entrada(mensaje_usuario)[0], "ts": reloj_iso(S)})
        hist.append({"rol": "assistant", "texto": salida["respuesta"], "ts": reloj_iso(S), "estado": salida["estado"],
                     "codigo": salida["codigo"], "tools": salida["tools_usadas"], "creditos": salida["creditos"]["consumidos"],
                     "alertas": salida["alertas_seguridad"], "request_id": salida["request_id"], "modelo": salida["modelo"]})


def _ruta(S, metodo, ruta, cuerpo, demo_id):
    uid = S["usuario_activo"]
    m = re.match(r"^/api/compras/(OC-\d{4})(/[a-z-]+)?$", ruta)

    if metodo == "GET" and ruta == "/api/estado":
        return vista.instantanea(S), False
    if metodo == "GET" and ruta == "/api/auditoria":
        return vista.auditoria(S), False
    if metodo == "GET" and ruta == "/api/pruebas":
        return {"catalogo": pruebas.catalogo(), "ultimos": S["pruebas"]}, False

    # ── Pruebas de aceptación (no tocan la demo en curso, salvo la prueba libre) ──
    if metodo == "POST" and ruta == "/api/pruebas/deterministas":
        S["pruebas"]["deterministas"] = {"ts": reloj_iso(S), "resultados": pruebas.correr_deterministas()}
        return {"deterministas": S["pruebas"]["deterministas"]}, True
    if metodo == "POST" and ruta == "/api/pruebas/caso":
        _limite_ia(S)
        r = pruebas.correr_caso(str(cuerpo.get("id", "")))
        previo = S["pruebas"]["casos"].get(r["id"]) or {}
        r["veredicto_final"] = previo.get("veredicto_final", "")
        S["pruebas"]["casos"][r["id"]] = r
        return {"caso": r}, True
    if metodo == "POST" and ruta == "/api/pruebas/veredicto":
        caso = S["pruebas"]["casos"].get(str(cuerpo.get("id", "")))
        if not caso:
            raise ErrorHTTP(404, "Primero ejecuta el caso")
        valor = cuerpo.get("valor", "")
        if valor not in ("", "PASS", "FAIL"):
            raise ErrorHTTP(422, "Veredicto inválido")
        caso["veredicto_final"] = valor
        return {"ok": True}, True
    if metodo == "POST" and ruta == "/api/pruebas/libre":
        _limite_ia(S)
        mensaje = str(cuerpo.get("mensaje", ""))[:2000]
        quien = cuerpo.get("usuario_id") or uid
        if not mensaje.strip():
            raise ErrorHTTP(422, "Escribe una pregunta.")
        if not any(u["usuario_id"] == quien for u in S["datos"]["USUARIOS"]):
            raise ErrorHTTP(422, "Usuario inexistente")
        salida = agente.ejecutar(S, mensaje, "consulta", quien)
        texto = mensaje if "PIN_ENMASCARADO" not in salida["alertas_seguridad"] else agente.revisar_entrada(mensaje)[0]
        S["pruebas"]["libres"].insert(0, {"ts": reloj_iso(S), "usuario_id": quien, "entrada": texto, "salida": salida})
        S["pruebas"]["libres"] = S["pruebas"]["libres"][:15]
        return {"libre": S["pruebas"]["libres"][0]}, True

    # ── Ciclo completo ──
    if metodo == "POST" and ruta == "/api/ciclo/aprobar-agente":
        return {"resultado": simulador.atajo_aprobar_agente(S, uid)}, True
    if metodo == "POST" and ruta == "/api/demo/llegada-todas":
        return {"resultado": simulador.simular_llegada_todas(S, uid)}, True

    if metodo == "POST" and ruta == "/api/demo/reiniciar":
        S.clear(); S.update(estado_inicial())
        return {"ok": True}, True
    if metodo == "POST" and ruta == "/api/demo/usuario":
        if not any(u["usuario_id"] == cuerpo.get("usuario_id") for u in S["datos"]["USUARIOS"]):
            raise ErrorHTTP(422, "Usuario inexistente")
        S["usuario_activo"] = cuerpo["usuario_id"]
        return {"ok": True}, True
    if metodo == "POST" and ruta == "/api/demo/config":
        simulador.cambiar_config(S, uid, cuerpo.get("campo"), cuerpo.get("valor"))
        return {"ok": True}, True
    if metodo == "POST" and ruta == "/api/demo/simular":
        return {"resultado": simulador.simular_ventas(S, uid, cuerpo.get("horas", 4), cuerpo.get("intensidad", 1.0))}, True
    if metodo == "POST" and ruta == "/api/demo/llegada":
        simulador.simular_llegada(S, uid, cuerpo.get("numero", ""))
        return {"ok": True}, True
    if metodo == "POST" and ruta == "/api/demo/excel":
        tablas = datos.leer_excel_b64(cuerpo.get("archivo_b64", ""))
        errores = datos.validar(tablas)
        if errores:
            raise ErrorHTTP(422, "El Excel tiene problemas: " + "; ".join(errores), "EXCEL_INVALIDO")
        S.clear(); S.update(estado_inicial(tablas))
        return {"ok": True, "productos": len(tablas["PRODUCTOS"]), "ventas": len(tablas["VENTAS_DIARIAS"])}, True
    if metodo == "POST" and ruta == "/api/notificaciones/leidas":
        for n in S["notificaciones"]:
            n["leida"] = True
        return {"ok": True}, True

    if metodo == "POST" and ruta in ("/api/ia/recompra", "/api/ia/corrida", "/api/ia/chat"):
        _limite_ia(S)
        if ruta == "/api/ia/recompra":
            salida = agente.ejecutar(S, "[TARJETA] Sugerir Recompra", "a_demanda", uid)
            _respuesta_ia(S, salida, "Sugerir Recompra")
        elif ruta == "/api/ia/corrida":
            simulador.ir_a_corrida(S)
            salida = agente.ejecutar(S, "", "programada", uid)
            _respuesta_ia(S, salida)
        else:
            mensaje = str(cuerpo.get("mensaje", ""))[:2000]
            if not mensaje.strip():
                raise ErrorHTTP(422, "Escribe una consulta.")
            salida = agente.ejecutar(S, mensaje, "consulta", uid, historial=S["chat"].get(uid, []))
            _respuesta_ia(S, salida, mensaje)
        return {"salida": salida}, True
    if metodo == "POST" and ruta == "/api/ia/chat/limpiar":
        S["chat"][uid] = []
        return {"ok": True}, True

    if metodo == "POST" and ruta == "/api/compras/enviar-aprobacion":
        return {"resultado": compras.enviar_a_aprobacion(S, uid, list(cuerpo.get("numeros", []))[:50])}, True
    if metodo == "POST" and ruta == "/api/compras/aprobar":
        return {"resultado": compras.aprobar(S, uid, list(cuerpo.get("numeros", []))[:50])}, True
    if metodo == "POST" and ruta == "/api/compras/deshacer":
        return compras.deshacer_aprobacion(S, uid, list(cuerpo.get("numeros", []))[:50]), True
    if metodo == "POST" and ruta == "/api/compras/enviar-lote":
        try:
            enviadas = compras.enviar_lote(S, uid, list(cuerpo.get("numeros", []))[:50], cuerpo.get("pin"), cuerpo.get("otp"))
        except compras.ErrorCompras:
            guardar(demo_id, S)
            raise
        return {"enviadas": [o["numero"] for o in enviadas]}, True
    if metodo == "POST" and ruta == "/api/compras/otp":
        return compras.solicitar_otp(S, uid), True
    if m:
        numero, accion = m.group(1), m.group(2)
        oc = next((o for o in S["ocs"] if o["numero"] == numero), None)
        if not oc:
            raise ErrorHTTP(404, f"No existe la orden {numero}", "NO_ENCONTRADA")
        if metodo == "GET" and accion is None:
            compras._exigir(S, uid, "ver", oc)
            return vista.oc_detalle(S, uid, oc), False
        if metodo == "POST" and accion == "/linea":
            compras.editar_linea(S, uid, numero, cuerpo.get("sku"), cuerpo.get("almacen_id"), cuerpo.get("cantidad"),
                                 cuerpo.get("costo_unitario"), bool(cuerpo.get("quitar")))
            return vista.oc_detalle(S, uid, oc), True
        if metodo == "POST" and accion == "/proveedor":
            compras.asignar_proveedor(S, uid, numero, cuerpo.get("proveedor_id"))
            return vista.oc_detalle(S, uid, oc), True
        if metodo == "POST" and accion == "/rechazar":
            compras.rechazar(S, uid, numero, cuerpo.get("motivo", ""))
            return vista.oc_detalle(S, uid, oc), True
        if metodo == "POST" and accion == "/enviar":
            try:
                compras.enviar_al_proveedor(S, uid, numero, cuerpo.get("pin"), cuerpo.get("otp"))
            except compras.ErrorCompras as exc:
                guardar(demo_id, S)          # los intentos fallidos de PIN deben quedar registrados
                raise exc
            return vista.oc_detalle(S, uid, oc), True
    raise ErrorHTTP(404, "Ruta no encontrada", "NO_ENCONTRADA")


def manejar(metodo, ruta, cabeceras, cuerpo_bytes):
    """Devuelve (status, cabeceras, cuerpo_bytes)."""
    ruta = ruta.split("?")[0].rstrip("/") or "/"
    cab = {k.lower(): v for k, v in cabeceras.items()}
    if ruta == "/api/salud":
        from .llm import ia_real_disponible, nombre_modelo
        return _json(200, {"ok": True, "almacen": ALMACEN.nombre, "ia_real": ia_real_disponible(), "modelo": nombre_modelo(),
                           "requiere_codigo": bool(os.environ.get("DEMO_CODIGO_ACCESO"))})
    codigo = os.environ.get("DEMO_CODIGO_ACCESO")
    if codigo and not hmac.compare_digest(cab.get("x-demo-codigo", ""), codigo):
        return _json(401, {"error": "Código de acceso inválido", "codigo": "CODIGO_ACCESO"})
    demo_id = cab.get("x-demo-id", "")
    if not re.match(r"^[a-zA-Z0-9-]{8,64}$", demo_id):
        return _json(400, {"error": "Falta el identificador de la demo", "codigo": "SIN_DEMO_ID"})
    if len(cuerpo_bytes or b"") > MAX_CUERPO:
        return _json(413, {"error": "El archivo supera 4 MB", "codigo": "MUY_GRANDE"})
    inicio = time.perf_counter()
    try:
        S = cargar(demo_id)
        if metodo == "GET" and ruta == "/api/demo/excel":
            contenido = datos.exportar_excel(S)
            return 200, {"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         "Content-Disposition": 'attachment; filename="datos_abastecimiento_demo.xlsx"', "Cache-Control": "no-store"}, contenido
        cuerpo = json.loads(cuerpo_bytes.decode("utf-8")) if cuerpo_bytes else {}
        if not isinstance(cuerpo, dict):
            raise ErrorHTTP(400, "Cuerpo inválido")
        resultado, cambia = _ruta(S, metodo, ruta, cuerpo, demo_id)
        if cambia:
            log_tecnico(S, {}, "api", ruta=ruta, metodo=metodo, status=200, latencia_ms=round((time.perf_counter() - inicio) * 1000))
            guardar(demo_id, S)
        if ruta != "/api/estado" and metodo == "POST":
            resultado = {**resultado, "estado": vista.instantanea(S)}
        return _json(200, resultado)
    except ErrorHTTP as exc:
        return _json(exc.status, {"error": str(exc), "codigo": exc.codigo})
    except compras.ErrorCompras as exc:
        return _json(exc.status, {"error": str(exc), "codigo": exc.codigo})
    except (ValueError, KeyError, TypeError) as exc:
        return _json(422, {"error": str(exc)[:200] or "Datos inválidos", "codigo": "VALIDACION"})
    except Exception as exc:
        traceback.print_exc()          # va al log de Vercel, nunca al cliente
        return _json(500, {"error": "Error interno. No se perdió nada: vuelve a intentarlo.", "codigo": type(exc).__name__})
