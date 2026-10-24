// App Shell: cabecera, menú lateral filtrado por permisos, enrutador y estado compartido entre las vistas.
import { api } from "./api.js";
import { esc, fechaLarga, icono, toast } from "./ui.js";
import { vistaIA } from "./ia.js";
import { vistaCompras, abrirOrden } from "./compras.js";
import { vistaStock } from "./stock.js";
import { vistaAuditoria } from "./auditoria.js";
import { vistaCiclo } from "./ciclo.js";
import { vistaPruebas } from "./pruebas.js";
import { abrirPanel, repintarPanel } from "./panel.js";

export const store = { estado: null };
let vistaActual = null;

export function setEstado(estado) {
  if (!estado) return;
  store.estado = estado;
  pintarShell();
  vistaActual?.actualizar?.(estado);
  repintarPanel();
}

export async function refrescar() {
  try { setEstado(await api("GET", "/api/estado")); }
  catch (e) { toast(e.message, { error: true }); }
}

// Ejecuta una acción de la API, actualiza el estado y muestra el error como toast.
export async function accion(metodo, ruta, cuerpo) {
  try {
    const r = await api(metodo, ruta, cuerpo);
    if (r.estado) setEstado(r.estado);
    return r;
  } catch (e) { toast(e.message, { error: true }); throw e; }
}

const NAV = [
  { id: "inicio", texto: "Inicio", icono: "inicio", bloqueado: true },
  { id: "pos", texto: "POS", icono: "pos", bloqueado: true },
  { id: "stock", texto: "Stock", icono: "stock", ruta: "#/stock", permiso: "stock.ver" },
  { id: "catalogo", texto: "Catálogo", icono: "catalogo", bloqueado: true },
  { id: "compras", texto: "Compras", icono: "compras", ruta: "#/compras", permiso: "compras.ver" },
  { id: "clientes", texto: "Clientes", icono: "clientes", bloqueado: true },
  { id: "reportes", texto: "Reportes", icono: "reportes", bloqueado: true },
  { id: "auditoria", texto: "Auditoría", icono: "auditoria", ruta: "#/auditoria" },
  { id: "ia", texto: "Asistente IA", icono: "ia", ruta: "#/ia", permiso: "ia.chat" },
  { sep: true, nota: "Para la demo" },
  { id: "ciclo", texto: "Ciclo completo", icono: "ciclo", ruta: "#/ciclo" },
  { id: "pruebas", texto: "Pruebas", icono: "pruebas", ruta: "#/pruebas" },
];

function pintarShell() {
  const e = store.estado; if (!e) return;
  document.getElementById("marca-nombre").textContent = e.tenant.nombre;
  document.querySelector("#reloj span").innerHTML = `<span class="largo">Hora simulada · </span>${esc(fechaLarga(e.reloj))}`;
  const u = e.usuario;
  document.getElementById("usr-nombre").textContent = u.nombre;
  document.getElementById("usr-rol").textContent = u.rol;
  document.getElementById("usr-avatar").textContent = (u.nombre || "?").slice(0, 1);
  const sel = document.getElementById("usr-select");
  sel.innerHTML = e.usuarios.map((x) => `<option value="${esc(x.id)}" ${x.id === u.id ? "selected" : ""}>${esc(x.nombre)} · ${esc(x.rol)}</option>`).join("");
  const sinLeer = e.notificaciones.filter((n) => !n.leida).length;
  document.getElementById("btn-notif").innerHTML = icono("campana") + (sinLeer ? `<span class="punto">${sinLeer}</span>` : "");
  const pendientesIA = e.bandeja.length;
  const rutaActual = (location.hash.split("/")[1] || "ia").split("?")[0];
  const porAprobar = e.kpis.por_aprobar.n + e.kpis.generadas_ia.borradores;
  document.getElementById("lateral").innerHTML = NAV.map((n) => {
    if (n.sep) return `<div class="nav-sep"></div><p class="nav-nota" style="padding-bottom:4px">${n.nota}</p>`;
    const sinPermiso = n.permiso && !u.puede[n.permiso];
    if (n.bloqueado || sinPermiso) {
      const motivo = n.bloqueado ? "Fuera de esta demo" : "Tu rol no tiene acceso";
      return `<span class="nav-item bloqueado" title="${motivo}">${icono(n.icono)}<span>${n.texto}</span></span>`;
    }
    const cuenta = n.id === "compras" && porAprobar ? porAprobar : n.id === "ia" && pendientesIA ? pendientesIA : n.id === "ciclo" && e.ciclo.vueltas ? `${e.ciclo.vueltas} ↻` : "";
    return `<a class="nav-item" href="${n.ruta}" ${rutaActual === n.id ? 'aria-current="page"' : ""}>${icono(n.icono)}<span>${n.texto}</span>${cuenta ? `<span class="cuenta">${cuenta}</span>` : ""}</a>`;
  }).join("") + `<div class="nav-sep"></div><p class="nav-nota">Demo del RF-CORE-AI-06. Las opciones en gris no forman parte de esta demostración.</p>`;
}

// ── Notificaciones (campanita) ─────────────────────────────
function abrirNotificaciones() {
  const e = store.estado;
  const ya = document.getElementById("pop-notif");
  if (ya) { ya.remove(); return; }
  const pop = document.createElement("div");
  pop.id = "pop-notif"; pop.className = "caja compacta";
  Object.assign(pop.style, { position: "fixed", top: "60px", right: "16px", width: "min(380px, 92vw)", zIndex: 50, maxHeight: "70vh", overflowY: "auto" });
  pop.innerHTML = `<div class="caja-cab"><h3>Notificaciones</h3></div>` + (e.notificaciones.length ? e.notificaciones.map((n) => `
    <a class="propuesta" href="${esc(n.enlace || "#/ia")}"><span style="flex:1"><b style="font-weight:${n.leida ? 400 : 600}">${esc(n.mensaje)}</b><small>${esc(fechaLarga(n.ts))}</small></span></a>`).join("")
    : `<p class="tenue peq">Sin notificaciones por ahora.</p>`);
  document.body.appendChild(pop);
  const cerrar = (ev) => { if (!pop.contains(ev.target) && ev.target.id !== "btn-notif") { pop.remove(); document.removeEventListener("click", cerrar, true); } };
  setTimeout(() => document.addEventListener("click", cerrar, true), 0);
  pop.addEventListener("click", (ev) => { if (ev.target.closest("a")) pop.remove(); });
  if (e.notificaciones.some((n) => !n.leida)) accion("POST", "/api/notificaciones/leidas", {}).catch(() => {});
}

// ── Tema: Oscuro (Zen Muted, por defecto) · Claro · Auto ────
const TEMAS = ["oscuro", "claro", "auto"];
const leerTema = () => { try { return localStorage.getItem("tema") || "oscuro"; } catch { return "oscuro"; } };
function aplicarTema(t) {
  const real = t === "auto" ? (matchMedia("(prefers-color-scheme: light)").matches ? "claro" : "oscuro") : t;
  document.documentElement.setAttribute("data-tema", real);
  const b = document.getElementById("btn-tema");
  b.innerHTML = icono(t === "oscuro" ? "luna" : t === "claro" ? "sol" : "auto");
  b.title = `Modo de apariencia: ${t === "oscuro" ? "Oscuro (Zen Muted)" : t === "claro" ? "Claro" : "Auto"}`;
}

// ── Enrutador ───────────────────────────────────────────────
function enrutar() {
  const [, seccion = "ia", extra] = location.hash.split("/");
  const nombre = seccion.split("?")[0];
  const raiz = document.getElementById("vista");
  const vistas = { ia: vistaIA, compras: vistaCompras, stock: vistaStock, auditoria: vistaAuditoria, ciclo: vistaCiclo, pruebas: vistaPruebas };
  const crear = vistas[nombre] || vistaIA;
  if (!vistaActual || vistaActual.nombre !== nombre) {
    vistaActual?.destruir?.();
    vistaActual = crear(raiz, store);
    vistaActual.nombre = nombre;
    raiz.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  } else {
    vistaActual.ruta?.(location.hash);
  }
  if (nombre === "compras" && extra && /^OC-\d{4}$/.test(extra)) abrirOrden(extra);
  document.getElementById("lateral").classList.remove("abierto");
  pintarShell();
}

async function iniciar() {
  document.getElementById("btn-menu").innerHTML = icono("menu");
  document.getElementById("btn-ia").innerHTML = icono("ia");
  document.getElementById("btn-panel").innerHTML = icono("panel", 16) + "Panel de demo";
  document.getElementById("btn-menu").addEventListener("click", () => document.getElementById("lateral").classList.toggle("abierto"));
  document.getElementById("btn-notif").addEventListener("click", abrirNotificaciones);
  document.getElementById("btn-panel").addEventListener("click", abrirPanel);
  document.getElementById("btn-tema").addEventListener("click", () => {
    const sig = TEMAS[(TEMAS.indexOf(leerTema()) + 1) % TEMAS.length];
    try { localStorage.setItem("tema", sig); } catch { /* sin almacenamiento */ }
    aplicarTema(sig);
  });
  document.getElementById("usr-select").addEventListener("change", async (ev) => {
    await accion("POST", "/api/demo/usuario", { usuario_id: ev.target.value });
    toast(`Ahora ves la demo como ${store.estado.usuario.nombre} · ${store.estado.usuario.rol}`);
  });
  aplicarTema(leerTema());
  matchMedia("(prefers-color-scheme: light)").addEventListener("change", () => leerTema() === "auto" && aplicarTema("auto"));
  window.addEventListener("hashchange", enrutar);
  if (!location.hash) history.replaceState(null, "", "#/ia");
  enrutar();
  await refrescar();
}

iniciar();
