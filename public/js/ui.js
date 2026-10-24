// Utilidades de interfaz: escape, formatos, íconos, toasts, drawer y modal (Calm Design).

export const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const soles = (n) => {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return "—";
  const [ent, dec] = Math.abs(Number(n)).toFixed(2).split(".");
  return (Number(n) < 0 ? "−" : "") + "S/ " + ent.replace(/\B(?=(\d{3})+(?!\d))/g, ".") + "," + dec;
};
export const conPunto = (t) => (/[.!?]$/.test(String(t)) ? String(t) : String(t) + ".");

const DIAS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const partes = (iso) => { const [f, h = "00:00"] = String(iso).split("T"); const [y, m, d] = f.split("-").map(Number); return { y, m, d, h: h.slice(0, 5) }; };
export const fechaCorta = (iso) => { if (!iso) return "—"; const p = partes(iso); return `${String(p.d).padStart(2, "0")}/${String(p.m).padStart(2, "0")}`; };
export const fechaHora = (iso) => { if (!iso) return "—"; const p = partes(iso); return `${p.d} ${MESES[p.m - 1]} · ${p.h}`; };
export const fechaLarga = (iso) => { if (!iso) return "—"; const p = partes(iso); const dia = new Date(Date.UTC(p.y, p.m - 1, p.d)).getUTCDay();
  return `${DIAS[dia]} ${p.d} ${MESES[p.m - 1]} · ${p.h}`; };
export const hora = (iso) => partes(iso).h;

const P = {
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  ia: '<path d="M12 3l1.8 4.6L18 9.5l-4.2 1.9L12 16l-1.8-4.6L6 9.5l4.2-1.9z"/><path d="M19 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z"/>',
  campana: '<path d="M6 8a6 6 0 1112 0c0 7 3 8 3 8H3s3-1 3-8"/><path d="M10 20a2 2 0 004 0"/>',
  luna: '<path d="M21 13A9 9 0 1111 3a7 7 0 0010 10z"/>',
  sol: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  auto: '<circle cx="12" cy="12" r="9"/><path d="M12 3v18" /><path d="M12 3a9 9 0 010 18z" fill="currentColor"/>',
  inicio: '<path d="M3 11l9-7 9 7v9a1 1 0 01-1 1h-5v-6H9v6H4a1 1 0 01-1-1z"/>',
  pos: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
  stock: '<path d="M21 8l-9-5-9 5 9 5 9-5z"/><path d="M3 8v8l9 5 9-5V8"/><path d="M12 13v8"/>',
  catalogo: '<path d="M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z"/>',
  compras: '<path d="M6 7h15l-2 9H8L6 3H3"/><circle cx="9" cy="20" r="1.5"/><circle cx="18" cy="20" r="1.5"/>',
  clientes: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0113 0"/><path d="M16 4.5a3.5 3.5 0 010 7M21.5 20a6.5 6.5 0 00-4-6"/>',
  reportes: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  auditoria: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
  ajustes: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 01-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 010-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 014 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 010 4h-.1a1.7 1.7 0 00-1.5 1z"/>',
  candado: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 018 0v4"/>',
  cerrar: '<path d="M6 6l12 12M18 6L6 18"/>',
  enviar: '<path d="M22 2L11 13M22 2l-7 20-4-9-9-4z"/>',
  carrito: '<path d="M6 7h15l-2 9H8L6 3H3"/><path d="M12 10v4M10 12h4"/>',
  caja: '<rect x="3" y="6" width="18" height="13" rx="2"/><path d="M3 10h18M7 15h3"/>',
  buscar: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
  escudo: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  alerta: '<path d="M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
  reloj: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  json: '<path d="M8 3H7a2 2 0 00-2 2v5a2 2 0 01-2 2 2 2 0 012 2v5a2 2 0 002 2h1M16 3h1a2 2 0 012 2v5a2 2 0 002 2 2 2 0 00-2 2v5a2 2 0 01-2 2h-1"/>',
  panel: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/>',
  ciclo: '<path d="M21 12a9 9 0 01-15.5 6.2M3 12a9 9 0 0115.5-6.2"/><path d="M21 4v5h-5M3 20v-5h5"/>',
  pruebas: '<path d="M9 3h6M10 3v6L4.5 18.5A2 2 0 006.2 21h11.6a2 2 0 001.7-2.5L14 9V3"/><path d="M7 15h10"/>',
  check: '<path d="M5 12l5 5L20 7"/>',
  venta: '<path d="M4 7h16l-1.5 12H5.5z"/><path d="M9 7a3 3 0 016 0"/>',
  camion: '<path d="M3 6h11v10H3zM14 10h4l3 3v3h-7"/><circle cx="7" cy="18" r="1.8"/><circle cx="17" cy="18" r="1.8"/>',
};
export const icono = (nombre, t = 20) =>
  `<svg width="${t}" height="${t}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[nombre] || ""}</svg>`;

// Toast periférico con auto-cierre a 3000 ms (Calm Design)
export function toast(mensaje, { accion, onAccion, error = false, ms = 3000 } = {}) {
  const cont = document.getElementById("toasts");
  const el = document.createElement("div");
  el.className = "toast" + (error ? " error" : "");
  el.innerHTML = `<span>${esc(mensaje)}</span>${accion ? `<button type="button">${esc(accion)}</button>` : ""}`;
  if (accion) el.querySelector("button").addEventListener("click", () => { el.remove(); onAccion && onAccion(); });
  cont.appendChild(el);
  setTimeout(() => el.remove(), accion ? Math.max(ms, 6000) : ms);
}

let drawerActual = null;
export function cerrarDrawer(silencioso = false) {
  if (!drawerActual) return;
  const d = drawerActual; drawerActual = null;
  d.velo.remove(); d.el.remove();
  document.removeEventListener("keydown", d.tecla);
  if (!silencioso && d.alCerrar) d.alCerrar();
}
export function abrirDrawer({ cabecera, cuerpo, pie = "", ancho = false, alCerrar, clase = "drawer" }) {
  cerrarDrawer(true);
  const velo = document.createElement("div"); velo.className = "velo";
  const el = document.createElement("aside");
  el.className = clase + (ancho ? " ancho" : ""); el.setAttribute("role", "dialog"); el.setAttribute("aria-modal", "true");
  el.innerHTML = `<div class="drawer-cab"><div style="flex:1;min-width:0">${cabecera}</div>
    <button class="boton-icono" data-cerrar aria-label="Cerrar">${icono("cerrar")}</button></div>
    <div class="drawer-cuerpo">${cuerpo}</div>${pie ? `<div class="drawer-pie">${pie}</div>` : ""}`;
  const tecla = (e) => { if (e.key === "Escape" && !document.querySelector(".modal")) cerrarDrawer(); };
  // conserva el foco y el scroll al volver a pintar el mismo drawer
  velo.addEventListener("click", () => cerrarDrawer());
  el.querySelector("[data-cerrar]").addEventListener("click", () => cerrarDrawer());
  document.addEventListener("keydown", tecla);
  document.body.append(velo, el);
  drawerActual = { el, velo, tecla, alCerrar };
  setTimeout(() => el.querySelector("[data-cerrar]").focus(), 0);
  return el;
}
export const drawerAbierto = () => drawerActual?.el || null;

// Modal: solo para gates de autorización (PIN) y decisiones irreversibles
export function abrirModal(html, { alCerrar } = {}) {
  const velo = document.createElement("div"); velo.className = "velo"; velo.style.zIndex = 69;
  const el = document.createElement("div"); el.className = "modal"; el.setAttribute("role", "dialog"); el.setAttribute("aria-modal", "true");
  el.innerHTML = html;
  const cerrar = () => { velo.remove(); el.remove(); document.removeEventListener("keydown", tecla); alCerrar && alCerrar(); };
  const tecla = (e) => { if (e.key === "Escape") cerrar(); };
  document.addEventListener("keydown", tecla);
  el.querySelectorAll("[data-cerrar]").forEach((b) => b.addEventListener("click", cerrar));
  document.body.append(velo, el);
  return { el, cerrar };
}

export function confirmar(titulo, texto, boton = "Confirmar") {
  return new Promise((res) => {
    let ok = false;
    const m = abrirModal(`<h2>${esc(titulo)}</h2><p class="sub">${esc(texto)}</p>
      <div class="fila" style="justify-content:flex-end;margin-top:24px"><button class="boton" data-cerrar>Cancelar</button>
      <button class="boton primario" data-ok>${esc(boton)}</button></div>`, { alCerrar: () => res(ok) });
    m.el.querySelector("[data-ok]").addEventListener("click", () => { ok = true; m.cerrar(); });
  });
}

// Texto del agente: escapa y convierte [AB-03] en una marca visual
export const textoAgente = (t) => esc(t).replace(/\[(AB-\d{2})\]/g, '<span class="regla" title="Regla del agente">$1</span>')
  .split(/\n{2,}/).map((p) => `<p>${p.replace(/\n/g, "<br>")}</p>`).join("");

export const NOMBRE_TOOL = {
  consultar_estado_agente: "estado del agente", buscar_producto: "catálogo", consultar_cola_quiebres: "cola de quiebres",
  consultar_stock: "stock", consultar_consumo_kardex: "ventas (Kardex)", calcular_cantidad_sugerida: "cantidad sugerida",
  consultar_oc_en_transito: "órdenes en tránsito", consultar_ultimo_proveedor: "último proveedor", listar_borradores_agente: "órdenes del agente",
  buscar_reglas_abastecimiento: "reglas", generar_propuesta_abastecimiento: "propuesta", crear_borradores_oc: "crear borradores",
};
