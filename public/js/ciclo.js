// Ciclo completo: venta → quiebre → el agente propone → apruebas → autorizas con PIN → llega la mercadería → se vende otra vez.
import { accion, store } from "./app.js";
import { api } from "./api.js";
import { abrirModal, conPunto, esc, fechaHora, icono, soles, toast } from "./ui.js";

const PASOS = [
  { id: "vender", titulo: "La tienda vende", corto: "Venta" },
  { id: "quiebre", titulo: "Se detecta el quiebre", corto: "Quiebre" },
  { id: "agente", titulo: "El agente propone", corto: "Agente" },
  { id: "aprobar", titulo: "Revisas y apruebas", corto: "Aprobación" },
  { id: "enviar", titulo: "Autorizas con tu PIN", corto: "PIN" },
  { id: "llegada", titulo: "Llega la mercadería", corto: "Llegada" },
];
const INDICE = { vender: 0, agente: 2, aprobar: 3, enviar: 4, llegada: 5 };
const TIPO = { venta: "Venta simulada", quiebre: "Quiebre detectado", propuesta: "Borrador del agente", aprobacion: "Aprobada", envio: "Enviada con PIN", llegada: "Mercadería recibida" };

export function vistaCiclo(raiz) {
  let ocupado = false;
  let recienCerrada = 0;
  raiz.innerHTML = `<h1>Ciclo de abastecimiento</h1>
    <p class="sub">Del quiebre al stock repuesto, paso a paso. Es el mismo flujo del ERP: el agente propone, tú revisas, apruebas y autorizas con tu PIN. Cuando llega la mercadería, la tienda vuelve a vender y el ciclo empieza otra vez.</p>
    <div id="ci-cuerpo" style="margin-top:24px"><div class="bento"><div class="caja esqueleto" style="grid-column:span 7;height:420px"></div><div class="caja esqueleto" style="grid-column:span 5;height:420px"></div></div></div>`;
  const cuerpo = raiz.querySelector("#ci-cuerpo");

  function anillo(c, activo) {
    const R = 128, cx = 180, cy = 180;
    const pos = (i) => { const a = (-90 + i * 60) * Math.PI / 180; return [cx + R * Math.cos(a), cy + R * Math.sin(a)]; };
    const largo = 2 * Math.PI * R;
    const avance = (activo / PASOS.length) * largo;
    const nodos = PASOS.map((p, i) => {
      const [x, y] = pos(i);
      const estado = i < activo ? "hecho" : i === activo ? "actual" : "pendiente";
      const etiquetaX = x + (x > cx + 5 ? 36 : x < cx - 5 ? -36 : 0);
      const etiquetaY = y + (Math.abs(x - cx) < 5 ? (y < cy ? -38 : 46) : 5);
      const ancla = x > cx + 5 ? "start" : x < cx - 5 ? "end" : "middle";
      return `<g class="nodo ${estado}">${estado === "actual" ? `<circle class="halo" cx="${x}" cy="${y}" r="26"/>` : ""}
        <circle cx="${x}" cy="${y}" r="24"/>
        ${estado === "hecho" ? `<path d="M${x - 8} ${y} l6 6 l11 -12" class="marca"/>` : `<text x="${x}" y="${y + 6}" class="num">${i + 1}</text>`}
        <text x="${etiquetaX}" y="${etiquetaY}" text-anchor="${ancla}" class="etq">${esc(p.corto)}</text></g>`;
    }).join("");
    return `<svg viewBox="-60 -30 480 420" class="anillo" role="img" aria-label="Paso ${activo + 1} de 6: ${esc(PASOS[activo].titulo)}">
      <circle cx="${cx}" cy="${cy}" r="${R}" class="pista"/>
      <circle cx="${cx}" cy="${cy}" r="${R}" class="progreso" stroke-dasharray="${avance} ${largo}" transform="rotate(-90 ${cx} ${cy})"/>
      ${nodos}
      <text x="${cx}" y="${cy - 8}" class="centro-grande">Vuelta ${c.vueltas + 1}</text>
      <text x="${cx}" y="${cy + 20}" class="centro-peq">Paso ${activo + 1} de 6</text></svg>`;
  }

  function siguiente(e, c, activo) {
    const p = PASOS[activo];
    const b = (attr, texto, clase = "primario", extra = "") => `<button class="boton ${clase}" ${attr} ${ocupado ? "disabled" : ""} ${extra}>${texto}</button>`;
    const cuerpos = {
      vender: [`Las ventas bajan el stock. Cuando un producto cruza su mínimo, el sistema lo avisa y queda en la cola del agente.${c.vueltas ? ` <b>Ya tienes stock repuesto para vender de nuevo.</b>` : ""}`,
        `${b("data-vender=24", `${icono("venta", 16)}Simular 1 día de ventas`)}${b("data-vender=72", "Simular 3 días", "")}`],
      agente: [`Hay <b>${c.cola}</b> producto${c.cola === 1 ? "" : "s"} en quiebre esperando al agente. Lo dispara la tarjeta «Sugerir Recompra» o la corrida programada de las ${esc(e.config.hora_corrida_programada)}.`,
        `${b("data-recompra", `${icono("ia", 16)}Sugerir Recompra ahora`)}${b("data-corrida", `Esperar a las ${esc(e.config.hora_corrida_programada)}`, "")}`],
      aprobar: [`El agente dejó <b>${c.por_revisar.length}</b> orden${c.por_revisar.length === 1 ? "" : "es"} por revisar: ${c.por_revisar.map(esc).join(", ")}. Revísalas en Compras (cantidades, proveedor y por qué de cada número) y apruébalas.`,
        `<a class="boton primario" href="#/compras?origen=IA">${icono("compras", 16)}Revisar en Compras</a>${b("data-atajo", "Atajo: aprobar todo lo del agente", "", 'title="Para la demo: completa el proveedor faltante con el más frecuente de su categoría, envía a aprobación y aprueba"')}`],
      enviar: [`<b>${c.por_enviar.length}</b> orden${c.por_enviar.length === 1 ? "" : "es"} aprobada${c.por_enviar.length === 1 ? "" : "s"} esperan tu autorización: ${c.por_enviar.map(esc).join(", ")}. El agente nunca envía por sí solo; sin tu PIN no sale nada.`,
        `${b("data-pin", `${icono("candado", 16)}Enviar con mi PIN`)}<a class="boton" href="#/compras">Una por una en Compras</a>`],
      llegada: [`<b>${c.en_camino.length}</b> orden${c.en_camino.length === 1 ? "" : "es"} del agente van en camino: ${c.en_camino.map(esc).join(", ")}. Mientras tanto, el agente no las vuelve a pedir porque las cuenta como «en tránsito».`,
        `${b("data-llegada", `${icono("camion", 16)}Simular la llegada del proveedor`)}`],
    };
    const [texto, acciones] = cuerpos[p.id === "quiebre" ? "agente" : p.id];
    return `<section class="caja" style="grid-column:span 5" aria-live="polite"><p class="tenue peq" style="margin:0 0 4px">Siguiente paso · ${activo + 1} de 6</p>
      <h2 style="font-size:22px;margin-bottom:10px">${esc(p.titulo)}</h2><p style="margin:0 0 20px;color:var(--texto-2)">${texto}</p>
      <div class="fila">${acciones}</div>
      ${recienCerrada ? `<div class="aviso" style="margin-top:20px;background:var(--verde-fondo)">${icono("ciclo")}<div><b>Vuelta ${recienCerrada} completada.</b> La mercadería llegó y el stock está repuesto: la tienda puede vender de nuevo.</div></div>` : ""}
      ${ocupado ? `<div style="margin-top:18px"><div class="esqueleto" style="height:12px;width:70%"></div></div>` : ""}</section>`;
  }

  function pintar(e) {
    const c = e.ciclo;
    const activo = INDICE[c.etapa] ?? 0;
    const ll = c.ultima_llegada;
    const kpi = (t, v, d) => `<div class="kpi" style="cursor:default"><small>${t}</small><b>${v}</b><span>${d}</span></div>`;
    cuerpo.innerHTML = `<div class="bento"><section class="caja ciclo-caja" style="grid-column:span 7">${anillo(c, activo)}</section>${siguiente(e, c, activo)}</div>
      <div class="bandeja" style="margin-top:16px">
        ${kpi("Vendido en la demo", `${c.unidades_vendidas} u.`, "con el simulador de ventas")}
        ${kpi("Productos en quiebre", c.en_quiebre, `${c.cola} en la cola del agente`)}
        ${kpi("Órdenes del agente en camino", c.en_camino.length, `${c.recibidas.length} ya recibidas`)}
        ${kpi("Vueltas completadas", c.vueltas, "venta → stock repuesto")}</div>
      <div class="bento" style="margin-top:16px">
        <section class="caja" style="grid-column:span 7"><div class="caja-cab"><h2>Stock repuesto en la última llegada</h2>${ll ? `<span class="tenue peq">${esc(fechaHora(ll.ts))}</span>` : ""}</div>
          ${ll && ll.lineas.length ? `<div style="overflow-x:auto;margin:0 -24px -24px"><table class="tabla"><thead><tr><th style="padding-left:24px">Producto</th><th>Orden</th><th class="der">Antes</th><th class="der">Ahora</th><th class="der">Mínimo</th><th></th></tr></thead><tbody>
            ${ll.lineas.map((l) => `<tr><td style="padding-left:24px"><b>${esc(l.producto)}</b><small>${esc(l.almacen)}</small></td><td>${l.origen === "AGENTE" ? '<span class="badge ia">IA</span> ' : ""}${esc(l.numero)}</td>
              <td class="der">${l.antes}</td><td class="der"><b>${l.despues}</b></td><td class="der">${l.minimo}</td>
              <td>${l.despues > l.minimo ? `<span class="badge verde">${icono("check", 12)}Listo para vender</span>` : `<span class="badge ambar">Aún bajo</span>`}</td></tr>`).join("")}</tbody></table></div>`
            : `<p class="tenue">Cuando llegue la primera orden verás aquí el stock antes y después, producto por producto.</p>`}</section>
        <section class="caja" style="grid-column:span 5"><div class="caja-cab"><h2>Lo que pasó</h2><a class="enlace peq" href="#/auditoria">Auditoría ›</a></div>
          ${c.eventos.length ? `<ol class="linea-tiempo">${c.eventos.map((v) => `<li class="${v.tipo === "propuesta" ? "agente" : v.tipo === "envio" ? "pin" : ""}">
            <b>${esc(TIPO[v.tipo])}${v.recurso && !v.recurso.startsWith("EVT") ? ` · ${esc(v.recurso)}` : ""}</b>
            <small>${esc(fechaHora(v.ts))} · ${esc(String(v.actor).startsWith("agente") ? "Agente" : String(v.actor).startsWith("core-stock") ? "Sistema" : "Rosa")}${v.detalle.unidades != null ? ` · ${v.detalle.unidades} u. vendidas, ${v.detalle.quiebres} quiebre(s)` : ""}${v.detalle.sku ? ` · ${esc(v.detalle.sku)}` : ""}</small></li>`).join("")}</ol>`
            : `<p class="tenue">Todavía no hay movimientos.</p>`}</section></div>`;
    enlazar(e);
  }

  async function correr(fn) {
    if (ocupado) return;
    ocupado = true; pintar(store.estado);
    try { await fn(); } catch { /* el error ya se mostró */ }
    finally { ocupado = false; pintar(store.estado); }
  }

  function enlazar(e) {
    cuerpo.querySelectorAll("[data-vender]").forEach((b) => b.addEventListener("click", () => correr(async () => {
      recienCerrada = 0;
      const r = await accion("POST", "/api/demo/simular", { horas: Number(b.dataset.vender), intensidad: 2 });
      const x = r.resultado;
      toast(x.nuevos_quiebres.length ? `Se vendieron ${x.unidades} u. (${soles(x.monto)}): ${x.nuevos_quiebres.length} producto(s) cruzaron su mínimo.` : `Se vendieron ${x.unidades} u. Ningún producto cruzó su mínimo: simula más días.`);
    })));
    cuerpo.querySelector("[data-recompra]")?.addEventListener("click", () => correr(async () => {
      const r = await accion("POST", "/api/ia/recompra", {});
      toast(r.salida.estado === "COMPLETADA" ? `El agente dejó ${r.salida.borradores_oc.length} borrador(es) por revisar.` : r.salida.respuesta);
    }));
    cuerpo.querySelector("[data-corrida]")?.addEventListener("click", () => correr(async () => {
      const r = await accion("POST", "/api/ia/corrida", {});
      toast(r.salida.estado === "COMPLETADA" ? `Corrida de las ${e.config.hora_corrida_programada}: ${r.salida.borradores_oc.length} borrador(es).` : r.salida.respuesta);
    }));
    cuerpo.querySelector("[data-atajo]")?.addEventListener("click", () => correr(async () => {
      const r = (await accion("POST", "/api/ciclo/aprobar-agente", {})).resultado;
      const extra = r.proveedor_asignado.map((x) => `${x.numero} → ${x.proveedor}`).join(", ");
      toast(conPunto(`Aprobadas ${r.aprobadas.join(", ") || "ninguna"}${extra ? `. Proveedor asignado: ${extra}` : ""}`));
    }));
    cuerpo.querySelector("[data-pin]")?.addEventListener("click", () => autorizar(e.ciclo.por_enviar));
    cuerpo.querySelector("[data-llegada]")?.addEventListener("click", () => correr(async () => {
      const r = (await accion("POST", "/api/demo/llegada-todas", {})).resultado;
      recienCerrada = r.vueltas;
      toast(`Llegó la mercadería de ${r.ordenes.join(", ")}. Vuelta ${r.vueltas} completada.`);
    }));
  }

  function autorizar(numeros) {
    let modo = store.estado.pin.bloqueado ? "otp" : "pin";
    const m = abrirModal("");
    const total = store.estado.ocs.filter((o) => numeros.includes(o.numero)).reduce((s, o) => s + (o.monto || 0), 0);
    const pintarModal = (error = "") => {
      const w = store.estado.whatsapp[0];
      m.el.innerHTML = `<div class="fila" style="gap:10px"><span class="marca-logo">${icono("candado", 18)}</span><h2>${modo === "pin" ? "Autoriza con tu PIN" : "Código por WhatsApp"}</h2></div>
        <p class="sub peq" style="margin-top:12px">Se enviarán ${numeros.length} orden${numeros.length > 1 ? "es" : ""} (${numeros.map(esc).join(", ")}) por ${soles(total)}. Las propuso el agente; las autorizas tú. Cada envío queda auditado con tu nombre.</p>
        <div class="pin-entrada"><input id="pin" ${modo === "pin" ? 'type="password" placeholder="••••"' : 'placeholder="000000"'} inputmode="numeric" maxlength="6" aria-label="${modo === "pin" ? "PIN" : "Código"}" style="width:210px;letter-spacing:.45em"></div>
        <p class="pin-error" role="alert">${esc(error)}</p>
        ${modo === "otp" && w ? `<div class="wsp" style="border:1px dashed var(--acento)"><b>Solo en la demo · WhatsApp a ${esc(w.para)}</b>${esc(w.texto)}</div>` : ""}
        <div class="fila entre" style="margin-top:12px">${modo === "pin" ? `<button class="enlace peq" data-otp>No tengo mi PIN · usar código por WhatsApp</button>` : "<span></span>"}
          <div class="fila"><button class="boton" data-cerrar>Cancelar</button><button class="boton primario" data-ok>Autorizar y enviar</button></div></div>`;
      m.el.querySelector("[data-cerrar]").addEventListener("click", m.cerrar);
      const inp = m.el.querySelector("#pin"); inp.focus();
      inp.addEventListener("keydown", (ev) => ev.key === "Enter" && enviar());
      m.el.querySelector("[data-ok]").addEventListener("click", enviar);
      m.el.querySelector("[data-otp]")?.addEventListener("click", otp);
    };
    async function otp() {
      try { await accion("POST", "/api/compras/otp", {}); modo = "otp"; pintarModal(); } catch (e) { pintarModal(e.message); }
    }
    async function enviar() {
      const valor = m.el.querySelector("#pin").value.trim();
      try {
        const r = await api("POST", "/api/compras/enviar-lote", { numeros, ...(modo === "pin" ? { pin: valor } : { otp: valor }) });
        m.cerrar();
        (await import("./app.js")).setEstado(r.estado);
        toast(`Enviaste ${r.enviadas.join(", ")} a sus proveedores. Ahora van en camino.`);
      } catch (e) {
        (await import("./app.js")).refrescar();
        if (e.codigo === "PIN_BLOQUEADO") { await otp(); pintarModal(e.message); return; }
        pintarModal(e.message);
      }
    }
    if (modo === "otp") otp(); else pintarModal();
  }

  if (store.estado) pintar(store.estado);
  return { actualizar: (e) => { if (!ocupado) pintar(e); } };
}
