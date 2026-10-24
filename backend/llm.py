"""Adaptadores del modelo.

- OpenRouterLLM: OpenRouter (API compatible con OpenAI) con el mismo modelo del notebook,
  nvidia/nemotron-3-ultra-550b-a55b:free, y tool calling nativo. Sin dependencias: usa urllib.
  La clave OPENROUTER_API_KEY vive solo en el servidor, nunca en el navegador.
- SimuladoLLM: sigue el mismo protocolo con reglas fijas. Es el respaldo si no hay clave o el modelo
  gratuito falla durante la demo (cuota, 429, caída), y el motor de las pruebas deterministas.

Protocolo común: responder(system, messages, tools, modo) -> {"stop_reason", "content": [bloques], "modelo"}
Internamente los mensajes usan bloques tool_use / tool_result; el adaptador los traduce al formato de OpenAI.
"""
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.request

MODELO_POR_DEFECTO = "nvidia/nemotron-3-ultra-550b-a55b:free"
URL_OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"


class ErrorModelo(Exception):
    def __init__(self, mensaje, status=None):
        super().__init__(mensaje)
        self.status = status


def _a_openai(system, messages):
    """Bloques tool_use/tool_result → mensajes de OpenAI (assistant.tool_calls y role=tool)."""
    salida = [{"role": "system", "content": system}]
    for m in messages:
        if isinstance(m["content"], str):
            salida.append({"role": m["role"], "content": m["content"]})
            continue
        if m["role"] == "assistant":
            texto = " ".join(b["text"] for b in m["content"] if b["type"] == "text").strip()
            llamadas = [{"id": b["id"], "type": "function",
                         "function": {"name": b["name"], "arguments": json.dumps(b["input"], ensure_ascii=False)}}
                        for b in m["content"] if b["type"] == "tool_use"]
            salida.append({"role": "assistant", "content": texto or None, **({"tool_calls": llamadas} if llamadas else {})})
        else:
            for b in m["content"]:
                if b["type"] == "tool_result":
                    salida.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": b["content"]})
    return salida


def _limpiar_texto(t):
    t = re.sub(r"<think>.*?</think>", "", t or "", flags=re.S)
    return re.sub(r"^\s*</?think>\s*", "", t).strip()


class OpenRouterLLM:
    nombre = "openrouter"

    def __init__(self):
        self.clave = os.environ["OPENROUTER_API_KEY"]
        self.modelo = os.environ.get("OPENROUTER_MODEL", MODELO_POR_DEFECTO)
        self.timeout = int(os.environ.get("OPENROUTER_TIMEOUT", "70"))

    def _post(self, cuerpo):
        req = urllib.request.Request(URL_OPENROUTER, data=json.dumps(cuerpo).encode(), method="POST", headers={
            "Authorization": f"Bearer {self.clave}", "Content-Type": "application/json",
            "HTTP-Referer": os.environ.get("OPENROUTER_REFERER", "https://vercel.app"), "X-Title": "Demo Abastecimiento Inteligente"})
        for intento in range(3):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    datos = json.loads(r.read().decode())
                if "error" in datos and not datos.get("choices"):
                    raise ErrorModelo(str(datos["error"].get("message", datos["error"]))[:200], datos["error"].get("code"))
                return datos
            except urllib.error.HTTPError as e:
                detalle = ""
                try:
                    detalle = json.loads(e.read().decode()).get("error", {}).get("message", "")
                except Exception:
                    pass
                if e.code in (429, 502, 503) and intento < 2:
                    espera = min(float(e.headers.get("Retry-After") or 4 * (intento + 1)), 10)
                    time.sleep(espera)
                    continue
                raise ErrorModelo(f"OpenRouter {e.code}: {detalle[:160]}", e.code)
            except (urllib.error.URLError, TimeoutError) as e:
                if intento < 1:
                    continue
                raise ErrorModelo(f"Sin respuesta de OpenRouter: {type(e).__name__}")
        raise ErrorModelo("OpenRouter no respondió tras varios intentos")

    def responder(self, system, messages, tools, modo):
        cuerpo = {"model": self.modelo, "messages": _a_openai(system, messages), "temperature": 0, "max_tokens": 4096}
        if tools:
            cuerpo["tools"] = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                                  "parameters": t["input_schema"]}} for t in tools]
            cuerpo["tool_choice"] = "auto"
        datos = self._post(cuerpo)
        msg = (datos.get("choices") or [{}])[0].get("message") or {}
        content = []
        texto = _limpiar_texto(msg.get("content") or "")
        if texto:
            content.append({"type": "text", "text": texto})
        for i, tc in enumerate(msg.get("tool_calls") or []):
            fn = tc.get("function") or {}
            try:
                argumentos = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                argumentos = {}
            content.append({"type": "tool_use", "id": tc.get("id") or f"call_{i}_{secrets.token_hex(3)}",
                            "name": fn.get("name", ""), "input": argumentos if isinstance(argumentos, dict) else {}})
        llamadas = any(b["type"] == "tool_use" for b in content)
        return {"stop_reason": "tool_use" if llamadas else "end_turn", "content": content, "modelo": self.modelo}


def ia_real_disponible() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY")) and os.environ.get("MODO_IA", "auto") != "simulado"


def nombre_modelo() -> str:
    return os.environ.get("OPENROUTER_MODEL", MODELO_POR_DEFECTO) if ia_real_disponible() else "IA simulada"


def obtener_llm(preferido="auto"):
    if preferido != "simulado" and ia_real_disponible():
        return OpenRouterLLM()
    return SimuladoLLM()


# ─────────────────────────────────────────────────────────────── IA simulada
ALMACEN_POR_PALABRA = {"huallaga": "ALM-01", "principal": "ALM-01", "cercado": "ALM-01", "gamarra": "ALM-02", "victoria": "ALM-02"}
PALABRAS_DOMINIO = ("stock", "pedi", "compr", "orden", "proveedor", "quiebre", "agente", "crédit", "credit", "hora", "tránsito",
                    "transito", "borrador", "cuánt", "cuant", "repon", "vend", "pin", "despach", "aprob", "regla", "product",
                    "sku", "collar", "arete", "pulsera", "anillo", "tobillera", "dije", "cadena", "broche", "set ", "llegar",
                    "camino", "lote", "eoq", "invent", "sugier", "recomiend", "por qué", "porque", "almac", "sucursal", "oc")
VACIAS = {"cuánto", "cuantas", "cuántas", "cuanto", "stock", "queda", "quedan", "hay", "del", "de", "la", "el", "los", "las", "en",
          "me", "recomiendas", "reponer", "pedir", "debería", "deberia", "por", "qué", "que", "almacén", "almacen", "sugeriste",
          "sugieres", "esa", "cantidad", "para", "unidades", "vendí", "vendi", "esta", "semana", "proveedor", "quién", "quien",
          "compro", "le", "a", "y", "huallaga", "gamarra", "mi", "mis", "se", "no", "si", "también", "estaban", "pidieron", "un", "una"}


def _tid():
    return "toolu_sim_" + secrets.token_hex(6)


def _texto_usuario(messages):
    for m in reversed(messages):
        if m["role"] == "user" and isinstance(m["content"], str):
            return m["content"]
    return ""


def _llamadas_previas(messages):
    """Pares (nombre_tool, resultado_json) en orden, desde el último mensaje de texto del usuario."""
    llamadas, ultimo_user = [], 0
    for i, m in enumerate(messages):
        if m["role"] == "user" and isinstance(m["content"], str):
            ultimo_user = i
    nombres = {}
    for m in messages[ultimo_user:]:
        if m["role"] == "assistant" and isinstance(m["content"], list):
            for b in m["content"]:
                if b.get("type") == "tool_use":
                    nombres[b["id"]] = b["name"]
        if m["role"] == "user" and isinstance(m["content"], list):
            for b in m["content"]:
                if b.get("type") == "tool_result":
                    try:
                        llamadas.append((nombres.get(b["tool_use_id"]), json.loads(b["content"])))
                    except (ValueError, TypeError):
                        llamadas.append((nombres.get(b["tool_use_id"]), {}))
    return llamadas


def _tool(nombre, **inp):
    return {"stop_reason": "tool_use", "content": [{"type": "tool_use", "id": _tid(), "name": nombre, "input": inp}], "modelo": "simulado"}


def _fin(texto):
    return {"stop_reason": "end_turn", "content": [{"type": "text", "text": texto}], "modelo": "simulado"}


def _soles(x):
    return "—" if x is None else f"S/ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class SimuladoLLM:
    nombre = "simulado"
    modelo = "simulado"

    def responder(self, system, messages, tools, modo):
        previas = _llamadas_previas(messages)
        if modo != "consulta":
            return self._corrida(previas)
        return self._consulta(_texto_usuario(messages), previas, {t["name"] for t in tools})

    # Corrida: generar → crear → resumen
    def _corrida(self, previas):
        if not previas:
            return _tool("generar_propuesta_abastecimiento")
        nombre, res = previas[-1]
        if nombre == "generar_propuesta_abastecimiento":
            if res.get("borradores_previstos"):
                return _tool("crear_borradores_oc", propuesta_id=res["propuesta_id"])
            return _fin("No había nada que reponer: los quiebres pendientes ya están cubiertos o no hay eventos nuevos [AB-02].")
        prop = next((r for n, r in previas if n == "generar_propuesta_abastecimiento"), {})
        b = prop.get("borradores_previstos", [])
        partes = [f"Dejé {len(b)} borrador(es) de orden de compra: " + "; ".join(
            f"{x['proveedor']} con {len(x['lineas'])} producto(s)" for x in b) + "."]
        if any(x["sin_proveedor_asignado"] for x in b):
            partes.append("Uno quedó sin proveedor asignado porque esos productos nunca se compraron: elige el proveedor al revisarlo [AB-05].")
        for x in prop.get("lineas_excluidas", []):
            partes.append(f"Excluí {x['sku']} en {x['almacen_id']}: {x['motivo']} [AB-04].")
        partes.append("Revisa y ajusta las cantidades en Compras; enviarlas al proveedor exige tu PIN [AB-07].")
        return _fin(" ".join(partes))

    # Consulta: reglas por intención
    def _consulta(self, texto, previas, disponibles):
        t = texto.lower()
        hechas = [n for n, _ in previas]
        res = {n: r for n, r in previas}
        if not any(p in t for p in PALABRAS_DOMINIO):
            return _fin("Fuera de alcance: solo respondo consultas sobre abastecimiento e inventario de tu negocio.")
        if re.search(r"despach|envi(a|á|ar|ala|ála).*(proveedor|orden)|aprueb|aprob|\bpin\b", t):
            return _fin("No puedo aprobar ni enviar órdenes desde el chat. Eso se hace en Compras: abre la orden, apruébala "
                        "y al pulsar «Enviar al proveedor» el sistema te pedirá tu PIN en una ventana segura [AB-07]. "
                        "Nunca escribas tu PIN en el chat.")
        if re.search(r"\b(crea|haz|hazme|genera|arma)\b.*(orden|oc|borrador|pedido)", t):
            return _fin("Desde el chat no creo órdenes. Usa la tarjeta «Sugerir Recompra» para que el agente consolide ahora "
                        "los quiebres acumulados, o espera la corrida programada de esta noche [AB-02].")
        if re.search(r"crédit|credit|a qué hora|que hora|qué hora|corre el agente|configur|alcance|cobertura", t):
            if "consultar_estado_agente" not in hechas:
                return _tool("consultar_estado_agente")
            e = res["consultar_estado_agente"]
            return _fin(f"El agente corre todos los días a las {e['hora_corrida_programada']} (hora de Lima), "
                        f"con alcance {e['alcance_modo'].replace('_', ' ').lower()} y {e['dias_cobertura']} días de cobertura. "
                        f"Te quedan {e['saldo_creditos']} créditos: cada corrida cuesta {e['costo_corrida']} y cada consulta "
                        f"{e['costo_consulta']}. Hay {e['eventos_pendientes']} quiebre(s) en cola [AB-08].")
        if re.search(r"lote econ|eoq|óptim|optim|por qué no calcul", t):
            if "buscar_reglas_abastecimiento" not in hechas:
                return _tool("buscar_reglas_abastecimiento", consulta="cálculo cantidad sugerida lote económico")
            return _fin("No calculo un lote económico (EOQ) porque el sistema no registra plazo de entrega, cantidad mínima "
                        "de compra ni costos de pedido y almacenamiento. Uso una cantidad sugerida: velocidad de venta × días "
                        "de cobertura, el mínimo configurado y lo que ya viene en camino [AB-03].")
        if re.search(r"borrador|dejaste|propuest|propusiste", t) and not re.search(r"por qué|porque", t):
            if "listar_borradores_agente" not in hechas:
                return _tool("listar_borradores_agente")
            r = res["listar_borradores_agente"]
            if not r.get("total"):
                return _fin("Todavía no hay órdenes propuestas por el agente. Pulsa «Sugerir Recompra» o espera la corrida programada.")
            filas = [f"{o['numero']} ({o['proveedor']}, {len(o['lineas'])} producto(s), {_soles(o['monto'])}, {o['estado'].replace('_', ' ').lower()})"
                     for o in r["ordenes"]]
            return _fin("Las órdenes que propuse son: " + "; ".join(filas) + ". Las revisas y apruebas en Compras.")
        if re.search(r"tránsito|transito|por llegar|en camino|llegan", t) and not re.search(r"por qué|porque", t):
            if "consultar_oc_en_transito" not in hechas:
                return _tool("consultar_oc_en_transito")
            r = res["consultar_oc_en_transito"]
            if r.get("permitido") is False:
                return _fin("No tienes permiso para ver las órdenes de compra [AB-11].")
            if not r.get("total_lineas"):
                return _fin("No hay órdenes en camino en este momento.")
            return _fin("Vienen en camino: " + "; ".join(f"{l['pendiente']} u. de {l['sku']} para {l['almacen_id']} ({l['oc']}, llega {l['fecha_estimada']})" for l in r["lineas"]) + ".")
        if re.search(r"quiebre|cola|qué falta|que falta|qué productos", t) and not re.search(r"por qué|porque", t):
            if "consultar_cola_quiebres" not in hechas:
                return _tool("consultar_cola_quiebres")
            r = res["consultar_cola_quiebres"]
            if not r.get("total"):
                return _fin("No hay quiebres pendientes en las sucursales que puedes ver.")
            return _fin(f"Hay {r['total']} quiebre(s) en cola: " + ", ".join(f"{e['producto']} en {e['almacen_id']}" for e in r["eventos"]) +
                        ". El agente los convertirá en borradores en su próxima corrida o al pulsar «Sugerir Recompra» [AB-02].")
        return self._producto(t, texto, hechas, res, previas)

    def _producto(self, t, texto, hechas, res, previas):
        m = re.search(r"\b[A-Z0-9]{2,5}(?:-[A-Z0-9]{1,5}){1,3}\b", texto.upper())
        sku = m.group(0) if m and "-" in m.group(0) and not m.group(0).startswith(("ALM-", "OC-", "SUC-")) else None
        if not sku:
            if "buscar_producto" not in hechas:
                palabras = " ".join(w for w in re.split(r"[^\wáéíóúñ]+", t) if w and w not in VACIAS)[:80] or t[:80]
                return _tool("buscar_producto", texto=palabras)
            b = res["buscar_producto"]
            if not b.get("encontrado"):
                return _fin(f"No encontré un producto que coincida con «{b.get('busqueda', '')}». ¿Puedes darme el código o el nombre exacto?")
            sku = b["coincidencias"][0]["sku"]
        almacen = next((v for k, v in ALMACEN_POR_PALABRA.items() if k in t), "")
        if re.search(r"proveedor|a quién|a quien", t):
            if "consultar_ultimo_proveedor" not in hechas:
                return _tool("consultar_ultimo_proveedor", sku=sku)
            r = res["consultar_ultimo_proveedor"]
            if r.get("permitido") is False:
                return _fin("No tienes permiso para ver compras [AB-11].")
            if not r.get("encontrado"):
                return _fin(f"No encontré el producto {sku}. Verifica el código.")
            if not r.get("proveedor_id"):
                return _fin(f"{sku} nunca se compró por el sistema: el agente lo deja en un borrador sin proveedor asignado [AB-05].")
            costo = f" a {_soles(r['costo_unitario'])} por unidad" if r.get("costo_unitario") is not None else ""
            return _fin(f"La última compra de {sku} fue a {r['proveedor']} el {r['fecha']}{costo}; a ese proveedor va el borrador [AB-05].")
        if re.search(r"vend", t):
            if "consultar_consumo_kardex" not in hechas:
                return _tool("consultar_consumo_kardex", sku=sku, almacen_id=almacen)
            r = res["consultar_consumo_kardex"]
            if r.get("permitido") is False:
                return _fin("No puedo mostrarte ese almacén: no tienes asignada esa sucursal [AB-11].")
            if not r.get("encontrado"):
                return _fin(f"No encontré el producto {sku}. Verifica el código.")
            return _fin(" ".join(f"En {c['almacen_id']} vendiste {c['vendidas_hoy']} hoy, {c['vendidas_7d']} en 7 días y {c['vendidas_30d']} en 30 días ({c['velocidad_diaria_30d']} por día)." for c in r["consumo"]))
        if re.search(r"cuánt\w* (debo|deber\w*|me recomiend\w*|pido|pedir|repon\w*|sugie\w*)|por qué|porque|recomiend|sugier|repon|pedir", t) and not re.search(r"cuánto stock|queda", t):
            if not almacen:
                if "consultar_stock" not in hechas:
                    return _tool("consultar_stock", sku=sku)
                st = res["consultar_stock"]
                if st.get("permitido") is False or not st.get("encontrado") or not st.get("stock"):
                    return _fin(f"No encontré stock visible para {sku}. Verifica el código o la sucursal.")
                almacen = min(st["stock"], key=lambda f: f["stock_disponible"] - f["stock_minimo"])["almacen_id"]
            if "calcular_cantidad_sugerida" not in hechas:
                return _tool("calcular_cantidad_sugerida", sku=sku, almacen_id=almacen)
            r = res["calcular_cantidad_sugerida"]
            if r.get("permitido") is False:
                return _fin("No puedo calcularlo para ese almacén: no tienes asignada esa sucursal [AB-11].")
            if not r.get("encontrado"):
                return _fin(f"No encontré {sku} en ese almacén. Verifica el código.")
            base = (f"Para {sku} en {r['almacen_id']} sugiero {r['cantidad_sugerida']} unidades. Vendes {r['velocidad_diaria']} por día "
                    f"({r['vendidas_en_ventana']} en {r['ventana_dias']} días); para cubrir {r['dias_cobertura']} días necesitas "
                    f"{r['reposicion_analytics']} más de las {r['stock_disponible']} que tienes, y para volver al mínimo de "
                    f"{r['stock_minimo']} faltan {r['faltante_al_minimo']}. Tomo la mayor: {r['necesidad']}.")
            if r["en_transito"]:
                base += f" Ya vienen {r['en_transito']} en camino ({', '.join(r['oc_en_transito'])}), así que las descuento."
            return _fin(base + " Es una cantidad sugerida que puedes editar, no un lote económico [AB-03].")
        if "consultar_stock" not in hechas:
            return _tool("consultar_stock", sku=sku, almacen_id=almacen)
        r = res["consultar_stock"]
        if r.get("permitido") is False:
            return _fin("No puedo mostrarte el stock de ese almacén: no tienes asignada esa sucursal [AB-11].")
        if r.get("error"):
            return _fin(f"No encontré el producto {sku}. Verifica el código.")
        if not r.get("encontrado"):
            return _fin(f"No encontré el producto {sku}. Verifica el código.")
        if not r["stock"]:
            return _fin(f"No hay stock visible de {sku} en tus sucursales.")
        return _fin(f"{r['producto']}: " + "; ".join(f"{f['stock_disponible']} u. en {f['almacen']} (mínimo {f['stock_minimo']})" for f in r["stock"]) + ".")
