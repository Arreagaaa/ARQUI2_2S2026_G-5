/**
 * Modulo de recepcion en tiempo real via Server-Sent Events (SSE).
 * Prohibido el polling a la base de datos o al servidor.
 * Retardo menor a 2 segundos garantizado por conexion reactiva directa.
 */

let eventSource = null;
let lastHeartbeatTimestamp = Date.now();

function initRealtimeStream() {
  if (eventSource) {
    eventSource.close();
  }

  eventSource = new EventSource('/api/stream/events');

  eventSource.onopen = function () {
    console.log('[SSE] Canal de eventos en vivo conectado exitosamente');
    updateLinkStatus(true);
  };

  eventSource.onmessage = function (event) {
    if (!event.data || event.data.trim() === '' || event.data.startsWith(':')) {
      return;
    }

    try {
      const payload = JSON.parse(event.data);
      lastHeartbeatTimestamp = Date.now();
      updateLinkStatus(true);

      if (payload.state) {
        renderSynopticState(payload.state);
      }

      // Si hay callbacks registrados por vistas especificas, invocarlos
      if (window.onRealtimeEvent) {
        window.onRealtimeEvent(payload);
      }
    } catch (err) {
      console.error('[SSE] Error procesando evento:', err, event.data);
    }
  };

  eventSource.onerror = function (err) {
    console.warn('[SSE] Error o desconexion en canal en vivo');
    updateLinkStatus(false);
  };
}

function updateLinkStatus(connected, lastIso) {
  const dot = document.getElementById('statusDot');
  const txt = document.getElementById('statusText');
  const banner = document.getElementById('linkAlertBanner');
  const tsSpan = document.getElementById('lastKnownTimestamp');

  if (connected) {
    if (dot) {
      dot.classList.remove('disconnected');
    }
    if (txt) {
      txt.textContent = 'CONECTADO';
      txt.style.color = 'var(--status-green)';
    }
    if (banner) {
      banner.style.display = 'none';
    }
  } else {
    if (dot) {
      dot.classList.add('disconnected');
    }
    if (txt) {
      txt.textContent = 'ENLACE PERDIDO';
      txt.style.color = 'var(--status-red)';
    }
    if (banner) {
      banner.style.display = 'block';
      if (tsSpan) {
        tsSpan.textContent = lastIso || new Date(lastHeartbeatTimestamp).toLocaleTimeString();
      }
    }
  }
}

function renderSynopticState(state) {
  if (!state) return;

  // Estado del enlace
  if (state.enlace === 'DESCONECTADO') {
    updateLinkStatus(false, state.ultimo_latido_timestamp);
  } else {
    updateLinkStatus(true);
  }

  // Marca de tiempo
  const tsEl = document.getElementById('syn-timestamp');
  if (tsEl && state.ultimo_latido_timestamp) {
    tsEl.textContent = new Date(state.ultimo_latido_timestamp).toLocaleTimeString();
  }

  // Modo
  const modoBadge = document.getElementById('syn-modo-badge');
  if (modoBadge && state.modo) {
    modoBadge.textContent = state.modo;
    if (state.modo === 'PARO_EMERGENCIA') {
      modoBadge.className = 'block-status-badge status-bloqueado';
    } else if (state.modo === 'MANTENIMIENTO') {
      modoBadge.className = 'block-status-badge status-ocupado';
    } else {
      modoBadge.className = 'block-status-badge status-libre';
    }
  }

  // Garita
  const garitaVal = document.getElementById('syn-garita-estado');
  const garitaVeh = document.getElementById('syn-garita-vehiculo');
  const garitaBadge = document.getElementById('syn-garita-badge');
  if (garitaVal && state.garita) {
    garitaVal.textContent = state.garita.estado || 'Libre';
    if (garitaVeh) garitaVeh.textContent = state.garita.vehiculo ? `UID: ${state.garita.vehiculo}` : 'Sin vehículo';
    if (garitaBadge) {
      garitaBadge.textContent = state.garita.estado || 'Libre';
      garitaBadge.className = 'block-status-badge ' + (state.garita.estado === 'Libre' ? 'status-libre' : 'status-ocupado');
    }
  }

  // Talanquera
  const talVal = document.getElementById('syn-talanquera-estado');
  const talBadge = document.getElementById('syn-talanquera-badge');
  if (talVal && state.talanquera) {
    talVal.textContent = state.talanquera;
    if (talBadge) {
      talBadge.textContent = state.talanquera;
      talBadge.className = 'block-status-badge ' + (state.talanquera.toUpperCase() === 'ABIERTA' ? 'status-libre' : 'status-ocupado');
    }
  }

  // Pesaje
  const pesVal = document.getElementById('syn-pesaje-valor');
  const pesEst = document.getElementById('syn-pesaje-estado');
  if (pesVal && state.pesaje) {
    pesVal.textContent = `${(state.pesaje.ultimo_valor_kg || 0).toFixed(2)} kg`;
    if (pesEst) pesEst.textContent = state.pesaje.estado || 'Libre';
  }

  // Aguja
  const aguVal = document.getElementById('syn-aguja-estado');
  const aguBadge = document.getElementById('syn-aguja-badge');
  if (aguVal && state.aguja) {
    aguVal.textContent = state.aguja;
    if (aguBadge) {
      aguBadge.textContent = state.aguja;
      aguBadge.className = 'block-status-badge ' + (state.aguja.toUpperCase() === 'RECTA' ? 'status-libre' : 'status-ocupado');
    }
  }

  // Transferencia
  const trVal = document.getElementById('syn-transf-estado');
  const trCam = document.getElementById('syn-transf-camion');
  if (trVal && state.transferencia) {
    trVal.textContent = state.transferencia.estado || 'Libre';
    if (trCam) trCam.textContent = state.transferencia.vehiculo || 'Sin camión';
  }

  // Grua
  const gruaEst = document.getElementById('syn-grua-estado');
  const gruaPos = document.getElementById('syn-grua-pos');
  const gruaBadge = document.getElementById('syn-grua-badge');
  const btnSusp = document.getElementById('btn-susp-grua');
  const btnRean = document.getElementById('btn-rean-grua');
  const btnRef = document.getElementById('btn-ref-grua');

  if (gruaEst && state.grua) {
    gruaEst.textContent = state.grua.estado || 'En reposo';
    if (gruaPos) {
      const posNombres = { 0: '0 (Transferencia)', 1: '1 (Patio P0)', 2: '2 (Patio P1)' };
      gruaPos.textContent = `Posición riel: ${posNombres[state.grua.posicion] || state.grua.posicion}`;
    }
    if (gruaBadge) {
      if (state.grua.en_falla) {
        gruaBadge.textContent = 'EN FALLA';
        gruaBadge.className = 'block-status-badge status-bloqueado';
      } else if (state.grua.suspendida) {
        gruaBadge.textContent = 'SUSPENDIDA';
        gruaBadge.className = 'block-status-badge status-alerta';
      } else {
        gruaBadge.textContent = state.grua.referenciada ? 'REFERENCIADA' : 'NO REFERENCIADA';
        gruaBadge.className = 'block-status-badge ' + (state.grua.referenciada ? 'status-libre' : 'status-alerta');
      }
    }

    // Actualizar condiciones de botones segun Seccion 4.1
    if (btnRean) btnRean.disabled = !state.grua.suspendida;
    if (btnRef) btnRef.disabled = !(state.grua.estado === 'En reposo' || state.grua.suspendida);
  }

  // Puerta de salida
  const salVal = document.getElementById('syn-salida-estado');
  const salBadge = document.getElementById('syn-salida-badge');
  if (salVal && state.puerta_salida) {
    salVal.textContent = state.puerta_salida;
    if (salBadge) {
      salBadge.textContent = state.puerta_salida;
      salBadge.className = 'block-status-badge ' + (state.puerta_salida.toUpperCase() === 'ABIERTA' ? 'status-libre' : 'status-ocupado');
    }
  }
}

// Watchdog de enlace en frontend: si pasan mas de 15 segundos sin ningun latido
setInterval(() => {
  const elapsed = (Date.now() - lastHeartbeatTimestamp) / 1000;
  if (elapsed > 15.0) {
    updateLinkStatus(false);
  }
}, 3000);

window.addEventListener('DOMContentLoaded', initRealtimeStream);
