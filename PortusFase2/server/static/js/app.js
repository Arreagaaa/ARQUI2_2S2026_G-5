/**
 * Logica cliente de interfaz de usuario para PORTUS Fase 2.
 * Maneja navegacion entre pestañas, modales, llamadas a la API REST,
 * confirmaciones de comandos remotos y renderizado de tablas.
 */

// -------------------------------------------------------------
// CAMBIO DE PESTAÑAS
// -------------------------------------------------------------
function switchTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));

  const targetPane = document.getElementById(tabId);
  if (targetPane) {
    targetPane.classList.add('active');
  }

  // Activar boton correspondiente
  const matchingBtn = Array.from(document.querySelectorAll('.tab-btn')).find(b =>
    b.getAttribute('onclick') && b.getAttribute('onclick').includes(tabId)
  );
  if (matchingBtn) {
    matchingBtn.classList.add('active');
  }
}

// -------------------------------------------------------------
// GESTION DE MODALES
// -------------------------------------------------------------
function openModal(id) {
  const m = document.getElementById(id);
  if (m) m.style.display = 'flex';
}

function closeModal(id) {
  const m = document.getElementById(id);
  if (m) m.style.display = 'none';
}

// -------------------------------------------------------------
// COMANDOS REMOTOS (ROL TERMINAL)
// -------------------------------------------------------------
async function sendRemoteCommand(comando, parametros = {}) {
  try {
    const resp = await fetch('/api/cmd/remote', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ comando, parametros })
    });
    const data = await resp.json();
    if (resp.ok) {
      console.log('[CMD]', data.message);
    } else {
      alert(`Error en comando '${comando}': ` + (data.error || 'Rechazado'));
    }
  } catch (err) {
    alert(`Fallo de comunicacion enviando comando '${comando}': ` + err);
  }
}

function confirmCommand(comando, mensaje, parametros = {}) {
  if (confirm(mensaje)) {
    sendRemoteCommand(comando, parametros);
  }
}

// -------------------------------------------------------------
// PESTAÑA TURNOS
// -------------------------------------------------------------
async function loadTurnos() {
  const estado = document.getElementById('filtro-turno-estado')?.value || '';
  const tipo = document.getElementById('filtro-turno-tipo')?.value || '';
  const q = document.getElementById('filtro-turno-q')?.value || '';

  const url = new URL('/api/turnos', window.location.origin);
  if (estado) url.searchParams.append('estado', estado);
  if (tipo) url.searchParams.append('tipo', tipo);
  if (q) url.searchParams.append('q', q);

  try {
    const resp = await fetch(url);
    const turnos = await resp.json();

    const tbodyActivos = document.getElementById('tabla-turnos-activos');
    const tbodyHistoricos = document.getElementById('tabla-turnos-historicos');

    if (!tbodyActivos) return;

    tbodyActivos.innerHTML = '';
    if (tbodyHistoricos) tbodyHistoricos.innerHTML = '';

    const activos = turnos.filter(t => t.estado_actual !== 'Cerrado' && t.estado_actual !== 'Anulado');
    const historicos = turnos.filter(t => t.estado_actual === 'Cerrado' || t.estado_actual === 'Anulado');

    if (activos.length === 0) {
      tbodyActivos.innerHTML = '<tr><td colspan="13" style="text-align: center; color: var(--text-muted);">No hay turnos activos</td></tr>';
    } else {
      activos.forEach(t => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${t.codigo_turno}</strong></td>
          <td>${t.placa_vehiculo}</td>
          <td>${t.transportista_id}</td>
          <td>${t.contenedor_id}</td>
          <td>${t.tipo_operacion}</td>
          <td><span class="block-status-badge status-libre">${t.estado_actual}</span></td>
          <td>${t.estacion_actual}</td>
          <td>${t.peso_declarado_g ? t.peso_declarado_g + ' g' : '--'}</td>
          <td>${t.peso_medido_entrada_g ? t.peso_medido_entrada_g + ' g' : '--'}</td>
          <td>${t.peso_medido_salida_g ? t.peso_medido_salida_g + ' g' : '--'}</td>
          <td>${t.posicion_patio_asignada !== null ? 'P' + t.posicion_patio_asignada : '--'}</td>
          <td>${t.tiempo_transcurrido_min} min</td>
          <td>
            <button class="btn-cmd" style="padding: 4px 8px; font-size: 11px;" onclick="openTimelineModal(${t.id}, '${t.codigo_turno}')">Línea Tiempo</button>
            <button class="btn-cmd" style="padding: 4px 8px; font-size: 11px;" onclick="retenerTurnoManualPrompt(${t.id})">Retener</button>
            <button class="btn-cmd danger" style="padding: 4px 8px; font-size: 11px;" onclick="anularTurnoPrompt(${t.id})">Anular</button>
          </td>
        `;
        tbodyActivos.appendChild(tr);
      });
    }

    if (tbodyHistoricos) {
      if (historicos.length === 0) {
        tbodyHistoricos.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-muted);">Sin turnos históricos</td></tr>';
      } else {
        historicos.forEach(t => {
          const badgeClass = t.estado_actual === 'Cerrado' ? 'status-libre' : 'status-alerta';
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td><strong>${t.codigo_turno}</strong></td>
            <td>${t.placa_vehiculo}</td>
            <td>${t.contenedor_id}</td>
            <td>${t.tipo_operacion}</td>
            <td><span class="block-status-badge ${badgeClass}">${t.estado_actual}</span></td>
            <td>${t.peso_medido_salida_g ? t.peso_medido_salida_g + ' g' : '--'}</td>
            <td>${Math.floor(t.tiempo_total_seg / 60)} min</td>
            <td>
              <button class="btn-cmd" style="padding: 4px 8px; font-size: 11px;" onclick="openTimelineModal(${t.id}, '${t.codigo_turno}')">Ver Detalle</button>
            </td>
          `;
          tbodyHistoricos.appendChild(tr);
        });
      }
    }
  } catch (err) {
    console.error('Error cargando turnos:', err);
  }
}

async function openTimelineModal(turnoId, codigo) {
  document.getElementById('timelineModalTitle').textContent = `Línea de Tiempo del Turno ${codigo}`;
  const tbody = document.getElementById('timelineModalBody');
  tbody.innerHTML = '<tr><td colspan="4" style="text-align: center;">Cargando eventos...</td></tr>';
  openModal('modalTimeline');

  try {
    const resp = await fetch(`/api/turnos/${turnoId}/timeline`);
    const events = await resp.json();
    tbody.innerHTML = '';
    if (events.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">Sin eventos registrados</td></tr>';
      return;
    }

    events.forEach(e => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td style="font-family: monospace; font-size: 11px;">${new Date(e.timestamp).toLocaleString()}</td>
        <td><strong>${e.origen}</strong></td>
        <td>${e.descripcion}</td>
        <td style="font-size: 11px; font-family: monospace; color: var(--accent-cyan);">${e.valores_asociados || '--'}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="4" style="color: var(--status-red);">Error cargando línea de tiempo: ${err}</td></tr>`;
  }
}

async function retenerTurnoManualPrompt(turnoId) {
  const obs = prompt('Ingrese observación para la retención manual (opcional):', 'Retención preventiva por operador');
  if (obs !== null) {
    try {
      const resp = await fetch(`/api/turnos/${turnoId}/retener-manual`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ observacion: obs })
      });
      const data = await resp.json();
      if (resp.ok) {
        alert(data.message);
        loadTurnos();
        loadRetenciones();
      } else {
        alert('Error: ' + data.error);
      }
    } catch (e) {
      alert('Fallo de red: ' + e);
    }
  }
}

async function anularTurnoPrompt(turnoId) {
  if (confirm('¿Confirma anular este turno y autorizar salida sin completar operación?')) {
    try {
      const resp = await fetch(`/api/turnos/${turnoId}/anular`, { method: 'POST' });
      const data = await resp.json();
      if (resp.ok) {
        alert(data.message);
        loadTurnos();
      } else {
        alert('Error: ' + data.error);
      }
    } catch (e) {
      alert('Fallo de red: ' + e);
    }
  }
}

// -------------------------------------------------------------
// PESTAÑA RETENCIONES (3 PLAZAS)
// -------------------------------------------------------------
let currentResolvingRetId = null;

async function loadRetenciones() {
  const causa = document.getElementById('filtro-ret-causa')?.value || '';
  const url = new URL('/api/retenciones', window.location.origin);
  if (causa) url.searchParams.append('causa', causa);

  try {
    const resp = await fetch(url);
    const list = await resp.json();

    const tbodyAbiertas = document.getElementById('tabla-retenciones-abiertas');
    const tbodyResueltas = document.getElementById('tabla-retenciones-resueltas');

    if (!tbodyAbiertas) return;

    tbodyAbiertas.innerHTML = '';
    if (tbodyResueltas) tbodyResueltas.innerHTML = '';

    const abiertas = list.filter(r => r.estado === 'ABIERTA');
    const resueltas = list.filter(r => r.estado === 'RESUELTA');

    // Actualizar plazas en el sinoptico
    const p1El = document.getElementById('syn-p1');
    const p2El = document.getElementById('syn-p2');
    const p3El = document.getElementById('syn-p3');
    const parkBadge = document.getElementById('syn-parqueo-badge');

    const plazasOcupadas = { 1: false, 2: false, 3: false };
    abiertas.forEach(r => {
      plazasOcupadas[r.plaza_numero] = r.vehiculo_placa;
    });

    if (p1El) p1El.innerHTML = plazasOcupadas[1] ? `<span style="color: var(--status-red);">${plazasOcupadas[1]}</span>` : `<span style="color: var(--status-green);">LIBRE</span>`;
    if (p2El) p2El.innerHTML = plazasOcupadas[2] ? `<span style="color: var(--status-red);">${plazasOcupadas[2]}</span>` : `<span style="color: var(--status-green);">LIBRE</span>`;
    if (p3El) p3El.innerHTML = plazasOcupadas[3] ? `<span style="color: var(--status-red);">${plazasOcupadas[3]}</span>` : `<span style="color: var(--status-green);">LIBRE</span>`;
    if (parkBadge) {
      const ocCount = abiertas.length;
      parkBadge.textContent = `${ocCount} / 3 Ocupadas`;
      parkBadge.className = 'block-status-badge ' + (ocCount === 3 ? 'status-bloqueado' : ocCount > 0 ? 'status-alerta' : 'status-libre');
    }

    if (abiertas.length === 0) {
      tbodyAbiertas.innerHTML = '<tr><td colspan="10" style="text-align: center; color: var(--text-muted);">Sin retenciones abiertas</td></tr>';
    } else {
      abiertas.forEach(r => {
        let evidenciaPeso = '--';
        if (r.peso_declarado_g && r.peso_medido_g) {
          evidenciaPeso = `Decl: ${r.peso_declarado_g}g | Med: ${r.peso_medido_g}g (Dif: ${r.diferencia_abs_g}g, ${r.diferencia_pct}%)`;
        }

        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${r.codigo_retencion}</strong></td>
          <td>${r.codigo_turno} / ${r.vehiculo_placa}</td>
          <td>${r.contenedor_id}</td>
          <td><span class="block-status-badge status-alerta">${r.causa}</span></td>
          <td>${r.estacion}</td>
          <td><strong>Plaza ${r.plaza_numero}</strong></td>
          <td>${r.tiempo_retencion_min} min</td>
          <td style="font-size: 11px;">${evidenciaPeso}</td>
          <td><strong>${r.rol_facultado}</strong></td>
          <td>
            <button class="btn-cmd" style="padding: 4px 8px; font-size: 11px;" onclick="openResolveModal(${r.id}, '${r.causa}', '${r.vehiculo_placa}', '${r.contenedor_id}', '${r.rol_facultado}')">Resolver</button>
          </td>
        `;
        tbodyAbiertas.appendChild(tr);
      });
    }

    if (tbodyResueltas) {
      if (resueltas.length === 0) {
        tbodyResueltas.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">Sin retenciones resueltas</td></tr>';
      } else {
        resueltas.forEach(r => {
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td><strong>${r.codigo_retencion}</strong></td>
            <td>${r.codigo_turno} / ${r.vehiculo_placa}</td>
            <td>${r.causa}</td>
            <td><span class="block-status-badge status-libre">${r.tipo_resolucion}</span></td>
            <td>${r.resuelto_por || '--'}</td>
            <td>${Math.floor(r.tiempo_retencion_seg / 60)} min</td>
            <td>${r.motivo_rechazo || r.observacion || '--'}</td>
          `;
          tbodyResueltas.appendChild(tr);
        });
      }
    }
  } catch (err) {
    console.error('Error cargando retenciones:', err);
  }
}

function openResolveModal(retId, causa, vehiculo, contenedor, rolFacultado) {
  currentResolvingRetId = retId;
  const info = document.getElementById('retResolveInfo');
  info.innerHTML = `
    <strong>Vehículo:</strong> ${vehiculo} | <strong>Contenedor:</strong> ${contenedor}<br>
    <strong>Causa:</strong> ${causa} | <strong>Rol Facultado:</strong> ${rolFacultado}
  `;

  document.getElementById('inputMotivoRechazo').value = '';
  document.getElementById('inputObsResolucion').value = '';
  document.getElementById('groupMotivoRechazo').style.display = 'none';

  openModal('modalResolverRet');
}

async function submitResolucion(tipo) {
  if (!currentResolvingRetId) return;

  const motivoRechazo = document.getElementById('inputMotivoRechazo').value.trim();
  const observacion = document.getElementById('inputObsResolucion').value.trim();

  if (tipo === 'RECHAZAR' && !motivoRechazo) {
    document.getElementById('groupMotivoRechazo').style.display = 'block';
    alert('Para rechazar la retención es OBLIGATORIO indicar el motivo.');
    return;
  }

  try {
    const resp = await fetch(`/api/retenciones/${currentResolvingRetId}/resolver`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        resolucion: tipo,
        motivo_rechazo: motivoRechazo,
        observacion: observacion
      })
    });
    const data = await resp.json();
    if (resp.ok) {
      alert(`Retención resuelta exitosamente mediante ${tipo}. Plaza ${data.plaza_liberada} liberada.`);
      closeModal('modalResolverRet');
      loadRetenciones();
      loadTurnos();
    } else {
      alert('Error resolviendo retención: ' + data.error);
    }
  } catch (err) {
    alert('Fallo de red: ' + err);
  }
}

// -------------------------------------------------------------
// PESTAÑA PATIO
// -------------------------------------------------------------
async function loadPatio() {
  try {
    const resp = await fetch('/api/patio');
    const items = await resp.json();

    const tbody = document.getElementById('tabla-inventario-patio');
    if (!tbody) return;

    tbody.innerHTML = '';
    items.forEach(it => {
      const tr = document.createElement('tr');
      const excesivoStyle = it.permanencia_excesiva ? 'color: var(--status-red); font-weight: 700;' : '';
      const bloqueadaBadge = it.bloqueada
        ? '<span class="block-status-badge status-bloqueado">BLOQUEADA</span>'
        : '<span class="block-status-badge status-libre">LIBRE</span>';

      tr.innerHTML = `
        <td><strong>Posición ${it.posicion}</strong></td>
        <td>Nivel ${it.nivel}</td>
        <td><strong>${it.contenedor_id || '--'}</strong></td>
        <td>${it.naviera_id || '--'}</td>
        <td>${it.peso_declarado_g ? it.peso_declarado_g + ' g' : '--'}</td>
        <td>${it.estado_autorizacion}</td>
        <td>${bloqueadaBadge}</td>
        <td>${it.ingreso_at ? new Date(it.ingreso_at).toLocaleString() : '--'}</td>
        <td style="${excesivoStyle}">${it.permanencia_str}</td>
        <td>${it.remociones}</td>
      `;
      tbody.appendChild(tr);

      // Actualizar sinoptico
      const synCell = document.getElementById(`syn-p${it.posicion}-n${it.nivel}`);
      if (synCell) {
        synCell.innerHTML = it.contenedor_id ? `<strong style="color: var(--accent-cyan);">${it.contenedor_id}</strong>` : `<span style="color: var(--text-muted);">LIBRE</span>`;
      }
    });
  } catch (err) {
    console.error('Error cargando patio:', err);
  }
}

async function bloquearPosicionPrompt(pos) {
  if (confirm(`¿Confirma bloquear la posición ${pos} del patio?`)) {
    const resp = await fetch(`/api/patio/posicion/${pos}/bloquear`, { method: 'POST' });
    const data = await resp.json();
    alert(data.message || data.error);
    loadPatio();
  }
}

async function liberarPosicion(pos) {
  const resp = await fetch(`/api/patio/posicion/${pos}/liberar`, { method: 'POST' });
  const data = await resp.json();
  alert(data.message || data.error);
  loadPatio();
}

function openYardModal(pos) {
  bloquearPosicionPrompt(pos);
}

// -------------------------------------------------------------
// PESTAÑA GRUA
// -------------------------------------------------------------
async function loadGruaHistory() {
  const limit = document.getElementById('filtro-grua-limit')?.value || 50;
  try {
    const resp = await fetch(`/api/grua/historial?limit=${limit}`);
    const rows = await resp.json();

    const tbody = document.getElementById('tabla-grua-ciclos');
    if (!tbody) return;

    tbody.innerHTML = '';
    let totalTiempo = 0;
    let fallas = 0;

    rows.forEach(r => {
      totalTiempo += r.tiempo_ciclo_seg;
      if (!r.exitoso) fallas++;

      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${r.id}</td>
        <td>${r.turno_id || '--'}</td>
        <td>${r.tipo_trabajo}</td>
        <td>${r.posicion_origen}</td>
        <td>${r.posicion_destino}</td>
        <td>${r.tiempo_ciclo_seg.toFixed(1)} s</td>
        <td>${r.distancia_recorrida_mm} mm</td>
        <td><span class="block-status-badge ${r.exitoso ? 'status-libre' : 'status-bloqueado'}">${r.exitoso ? 'OK' : 'FALLA'}</span></td>
        <td>${r.evento_falla || '--'}</td>
        <td style="font-size: 11px;">${new Date(r.timestamp).toLocaleTimeString()}</td>
      `;
      tbody.appendChild(tr);
    });

    const statCiclos = document.getElementById('grua-stat-ciclos');
    const statProm = document.getElementById('grua-stat-promedio');
    const statFallas = document.getElementById('grua-stat-fallas');

    if (statCiclos) statCiclos.textContent = rows.length;
    if (statProm) statProm.textContent = rows.length > 0 ? (totalTiempo / rows.length).toFixed(1) + ' s' : '0.0 s';
    if (statFallas) statFallas.textContent = fallas;
  } catch (err) {
    console.error('Error cargando historial de grúa:', err);
  }
}

function exportGruaCSV() {
  window.open('/api/reportes/exportar-csv', '_blank');
}

// -------------------------------------------------------------
// PESTAÑA ALARMAS
// -------------------------------------------------------------
async function loadAlarmas() {
  const sev = document.getElementById('filtro-alarma-sev')?.value || '';
  const url = new URL('/api/alarmas', window.location.origin);
  if (sev) url.searchParams.append('severidad', sev);

  try {
    const resp = await fetch(url);
    const data = await resp.json();

    const tbodyActivas = document.getElementById('tabla-alarmas-activas');
    const tbodyHist = document.getElementById('tabla-alarmas-historicas');

    if (!tbodyActivas) return;

    tbodyActivas.innerHTML = '';
    if (tbodyHist) tbodyHist.innerHTML = '';

    if (data.activas.length === 0) {
      tbodyActivas.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--status-green);">No hay alarmas activas</td></tr>';
    } else {
      data.activas.forEach(a => {
        const sevClass = a.severidad === 'Critica' ? 'status-bloqueado' : a.severidad === 'Alta' ? 'status-alerta' : 'status-ocupado';
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${a.id}</td>
          <td><strong>${a.codigo}</strong></td>
          <td><span class="block-status-badge ${sevClass}">${a.severidad}</span></td>
          <td>${a.descripcion}</td>
          <td>${a.origen}</td>
          <td style="font-size: 11px;">${new Date(a.timestamp).toLocaleString()}</td>
          <td>
            <button class="btn-cmd" style="padding: 4px 8px; font-size: 11px;" onclick="reconocerAlarmaPrompt(${a.id})">Reconocer</button>
          </td>
        `;
        tbodyActivas.appendChild(tr);
      });
    }

    if (tbodyHist) {
      if (data.historicas.length === 0) {
        tbodyHist.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">Sin historial de alarmas</td></tr>';
      } else {
        data.historicas.forEach(a => {
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td>${a.id}</td>
            <td><strong>${a.codigo}</strong></td>
            <td>${a.severidad}</td>
            <td>${a.descripcion}</td>
            <td>${a.reconocida_por || '--'}</td>
            <td style="font-size: 11px;">${a.reconocida_en ? new Date(a.reconocida_en).toLocaleString() : '--'}</td>
            <td>${a.comentario_reconocimiento || '--'}</td>
          `;
          tbodyHist.appendChild(tr);
        });
      }
    }
  } catch (err) {
    console.error('Error cargando alarmas:', err);
  }
}

async function reconocerAlarmaPrompt(alarmId) {
  const comentario = prompt('Comentario de reconocimiento (opcional):', 'Condición verificada');
  try {
    const resp = await fetch(`/api/alarmas/${alarmId}/reconocer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ comentario })
    });
    const data = await resp.json();
    if (resp.ok) {
      loadAlarmas();
    } else {
      alert('Error: ' + data.error);
    }
  } catch (e) {
    alert('Fallo de red: ' + e);
  }
}

async function reconocerTodasBajasMedias() {
  try {
    const resp = await fetch('/api/alarmas/reconocer-todas', { method: 'POST' });
    const data = await resp.json();
    alert(data.message);
    loadAlarmas();
  } catch (e) {
    alert('Fallo de red: ' + e);
  }
}

// -------------------------------------------------------------
// PESTAÑA CITAS
// -------------------------------------------------------------
async function loadCitas() {
  const fechaInput = document.getElementById('filtro-cita-fecha');
  const fecha = fechaInput ? fechaInput.value : '';
  const url = new URL('/api/citas', window.location.origin);
  if (fecha) url.searchParams.append('fecha', fecha);

  try {
    const resp = await fetch(url);
    const citas = await resp.json();

    const tbody = document.getElementById('tabla-agenda-citas');
    if (!tbody) return;

    tbody.innerHTML = '';
    if (citas.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No hay citas agendadas para esta fecha</td></tr>';
      return;
    }

    citas.forEach(c => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><strong>${c.hora_inicio} - ${c.hora_fin}</strong></td>
        <td>Máx 2 citas</td>
        <td>1 asignada</td>
        <td>${c.transportista_id}</td>
        <td><strong>${c.contenedor_id}</strong></td>
        <td><span class="block-status-badge status-libre">${c.estado}</span></td>
        <td>${c.cumplida_en_ventana ? 'EN VENTANA (OK)' : 'PENDIENTE'}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error('Error cargando citas:', err);
  }
}

function generarCodigoModal() {
  document.getElementById('codigoResultBox').style.display = 'none';
  openModal('modalVinculacion');
}

async function ejecutarGeneracionCodigo() {
  const sel = document.getElementById('selTransVinculacion').value;
  try {
    const resp = await fetch('/api/transportista/generar-codigo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ transportista_id: sel })
    });
    const data = await resp.json();
    if (resp.ok) {
      document.getElementById('codigoGeneradoVal').textContent = data.codigo;
      document.getElementById('comandoVinculacionSugerido').textContent = `/vincular ${data.codigo}`;
      document.getElementById('codigoResultBox').style.display = 'block';
    } else {
      alert('Error: ' + data.error);
    }
  } catch (e) {
    alert('Fallo de red: ' + e);
  }
}

// -------------------------------------------------------------
// PESTAÑA REPORTES (8 METRICAS)
// -------------------------------------------------------------
async function calcularMetricasReporte() {
  const ini = document.getElementById('reporte-inicio').value;
  const fin = document.getElementById('reporte-fin').value;

  const url = new URL('/api/reportes/calcular', window.location.origin);
  if (ini) url.searchParams.append('inicio', new Date(ini).toISOString());
  if (fin) url.searchParams.append('fin', new Date(fin).toISOString());

  try {
    const resp = await fetch(url);
    const m = await resp.json();

    document.getElementById('met-remociones').textContent = m.remociones_por_contenedor_retirado;
    document.getElementById('met-ciclos').textContent = m.ciclos_grua_por_operacion;
    document.getElementById('met-distancia').textContent = m.distancia_total_grua_m + ' m';
    document.getElementById('met-tiempo-camion').textContent = m.tiempo_promedio_camion_seg + ' s (' + m.tiempo_promedio_camion_min + ' min)';
    document.getElementById('met-tiempo-retencion').textContent = m.tiempo_promedio_retencion_seg + ' s (' + m.tiempo_promedio_retencion_min + ' min)';
    document.getElementById('met-max-espera').textContent = m.longitud_maxima_fila_espera;
    document.getElementById('met-citas-pct').textContent = m.porcentaje_citas_cumplidas_ventana + '%';
    document.getElementById('met-retenciones-desglose').textContent = m.retenciones_desglose.length + ' grupos de causas';
  } catch (err) {
    alert('Error calculando métricas: ' + err);
  }
}

async function descargarReporteCSV() {
  const etiqueta = document.getElementById('reporte-etiqueta').value.trim() || 'Corrida';
  const ini = document.getElementById('reporte-inicio').value;
  const fin = document.getElementById('reporte-fin').value;

  try {
    const resp = await fetch('/api/reportes/exportar-csv', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        etiqueta,
        inicio: ini ? new Date(ini).toISOString() : null,
        fin: fin ? new Date(fin).toISOString() : null
      })
    });

    const blob = await resp.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `reporte_${etiqueta.replace(/\s+/g, '_')}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } catch (e) {
    alert('Error exportando reporte: ' + e);
  }
}

// -------------------------------------------------------------
// VISTAS NAVIERA, AGENTE Y AUTORIDAD
// -------------------------------------------------------------
async function loadNavieraData() {
  try {
    const resp = await fetch('/api/manifiestos');
    const rows = await resp.json();

    const tbodyManif = document.getElementById('tabla-naviera-manifiestos');
    const tbodyCont = document.getElementById('tabla-naviera-contenedores');

    if (tbodyManif) {
      tbodyManif.innerHTML = '';
      if (rows.length === 0) {
        tbodyManif.innerHTML = '<tr><td colspan="9" style="text-align: center; color: var(--text-muted);">No ha declarado manifiestos</td></tr>';
      } else {
        rows.forEach(m => {
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td><strong>${m.id}</strong></td>
            <td><strong>${m.contenedor_id}</strong></td>
            <td>${m.tipo_operacion}</td>
            <td>${m.peso_declarado_g} g</td>
            <td>${m.tolerancia_pct}%</td>
            <td>${m.transportista_id}</td>
            <td><span class="block-status-badge status-libre">${m.estado_documental}</span></td>
            <td>${m.canal_selectivo || 'Pendiente'}</td>
            <td>
              ${m.estado_documental === 'CREADO' ? `<button class="btn-cmd danger" style="padding: 4px 8px; font-size: 11px;" onclick="anularManifiesto('${m.id}')">Anular</button>` : '--'}
            </td>
          `;
          tbodyManif.appendChild(tr);
        });
      }
    }

    if (tbodyCont) {
      tbodyCont.innerHTML = '';
      rows.forEach(m => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${m.contenedor_id}</strong></td>
          <td>Patio / Por ingresar</td>
          <td>${m.peso_declarado_g} g</td>
          <td>${m.estado_documental}</td>
          <td>--</td>
        `;
        tbodyCont.appendChild(tr);
      });
    }
  } catch (e) {
    console.error('Error naviera:', e);
  }
}

function openNewManifiestoModal() {
  openModal('modalNuevoManifiesto');
}

async function submitNuevoManifiesto(e) {
  e.preventDefault();
  const body = {
    contenedor_id: document.getElementById('manif-contenedor').value,
    tipo_operacion: document.getElementById('manif-tipo').value,
    peso_declarado: document.getElementById('manif-peso').value,
    tolerancia: document.getElementById('manif-tolerancia').value,
    transportista_id: document.getElementById('manif-transportista').value,
    observaciones: document.getElementById('manif-obs').value
  };

  try {
    const resp = await fetch('/api/manifiestos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const data = await resp.json();
    if (resp.ok) {
      alert(data.message);
      closeModal('modalNuevoManifiesto');
      loadNavieraData();
    } else {
      alert('Error declarando manifiesto: ' + data.error);
    }
  } catch (err) {
    alert('Fallo de red: ' + err);
  }
}

async function anularManifiesto(id) {
  if (confirm(`¿Confirma anular el manifiesto ${id}?`)) {
    const resp = await fetch(`/api/manifiestos/${id}/anular`, { method: 'POST' });
    const data = await resp.json();
    alert(data.message || data.error);
    loadNavieraData();
  }
}

// -------------------------------------------------------------
// VISTA AGENTE
// -------------------------------------------------------------
async function loadAgenteData() {
  try {
    const resp = await fetch('/api/manifiestos');
    const rows = await resp.json();

    const tbody = document.getElementById('tabla-agente-pendientes');
    const tbodySeg = document.getElementById('tabla-agente-seguimiento');

    if (!tbody) return;

    tbody.innerHTML = '';
    if (tbodySeg) tbodySeg.innerHTML = '';

    rows.forEach(m => {
      // Manifiestos sin levante
      if (m.estado_documental !== 'LEVANTE_OTORGADO') {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${m.id}</strong></td>
          <td>${m.contenedor_id}</td>
          <td>${m.naviera_id}</td>
          <td>${m.tipo_operacion}</td>
          <td>${m.peso_declarado_g} g</td>
          <td><span class="block-status-badge status-libre">${m.estado_documental}</span></td>
          <td>
            ${m.estado_documental === 'CREADO' ? `<button class="btn-cmd" style="padding: 4px 8px; font-size: 11px;" onclick="openDeclaracionModal('${m.id}')">Presentar Declaración</button>` : ''}
            ${m.estado_documental === 'DECLARADO' ? `<button class="btn-cmd" style="padding: 4px 8px; font-size: 11px;" onclick="solicitarLevante('${m.id}')">Solicitar Levante</button>` : ''}
          </td>
        `;
        tbody.appendChild(tr);
      }

      if (tbodySeg) {
        const trSeg = document.createElement('tr');
        trSeg.innerHTML = `
          <td>${m.id}</td>
          <td><strong>${m.contenedor_id}</strong></td>
          <td>${m.estado_documental}</td>
          <td>${m.canal_selectivo || 'N/A'}</td>
          <td>${m.observaciones || '--'}</td>
        `;
        tbodySeg.appendChild(trSeg);
      }
    });
  } catch (e) {
    console.error('Error agente:', e);
  }
}

function openDeclaracionModal(manifId) {
  document.getElementById('dec-manifiesto-id').value = manifId;
  document.getElementById('dec-numero').value = `DEC-2026-${Math.floor(100 + Math.random() * 900)}`;
  openModal('modalDeclaracion');
}

async function submitDeclaracion(e) {
  e.preventDefault();
  const body = {
    manifiesto_id: document.getElementById('dec-manifiesto-id').value,
    numero_declaracion: document.getElementById('dec-numero').value,
    regimen: document.getElementById('dec-regimen').value,
    descripcion_mercancia: document.getElementById('dec-desc').value,
    valor_declarado: document.getElementById('dec-valor').value,
    observaciones: document.getElementById('dec-obs').value
  };

  try {
    const resp = await fetch('/api/declaraciones', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const data = await resp.json();
    if (resp.ok) {
      alert(data.message);
      closeModal('modalDeclaracion');
      loadAgenteData();
    } else {
      alert('Error: ' + data.error);
    }
  } catch (err) {
    alert('Fallo de red: ' + err);
  }
}

async function solicitarLevante(manifId) {
  try {
    const resp = await fetch('/api/declaraciones/solicitar-levante', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ manifiesto_id: manifId })
    });
    const data = await resp.json();
    if (resp.ok) {
      alert(data.message);
      loadAgenteData();
    } else {
      alert('Error: ' + data.error);
    }
  } catch (e) {
    alert('Fallo de red: ' + e);
  }
}

// -------------------------------------------------------------
// VISTA AUTORIDAD (SAT)
// -------------------------------------------------------------
let currentResolvingLevanteId = null;

async function loadAutoridadData() {
  try {
    const resp = await fetch('/api/manifiestos');
    const rows = await resp.json();

    const tbody = document.getElementById('tabla-autoridad-solicitudes');
    const tbodyCarga = document.getElementById('tabla-autoridad-carga');

    if (tbody) {
      tbody.innerHTML = '';
      const pendientes = rows.filter(m => m.estado_documental === 'LEVANTE_SOLICITADO');
      if (pendientes.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No hay solicitudes de levante pendientes</td></tr>';
      } else {
        pendientes.forEach(m => {
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td><strong>${m.id}</strong></td>
            <td><strong>${m.contenedor_id}</strong></td>
            <td>${m.naviera_id}</td>
            <td>${m.transportista_id}</td>
            <td>${m.peso_declarado_g} g</td>
            <td><span class="block-status-badge status-ocupado">${m.estado_documental}</span></td>
            <td>
              <button class="btn-cmd" style="padding: 4px 8px; font-size: 11px;" onclick="openLevanteModal('${m.id}', '${m.contenedor_id}')">Evaluar Levante</button>
            </td>
          `;
          tbody.appendChild(tr);
        });
      }
    }

    if (tbodyCarga) {
      tbodyCarga.innerHTML = '';
      rows.forEach(m => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${m.contenedor_id}</strong></td>
          <td>${m.naviera_id}</td>
          <td>Patio / En tránsito</td>
          <td>${m.peso_declarado_g} g</td>
          <td><span class="block-status-badge status-libre">${m.estado_documental}</span></td>
          <td>--</td>
        `;
        tbodyCarga.appendChild(tr);
      });
    }
  } catch (e) {
    console.error('Error autoridad:', e);
  }
}

async function loadRetencionesAduaneras() {
  try {
    const resp = await fetch('/api/retenciones');
    const list = await resp.json();

    const tbody = document.getElementById('tabla-autoridad-retenciones');
    if (!tbody) return;

    tbody.innerHTML = '';
    if (list.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" style="text-align: center; color: var(--text-muted);">No hay retenciones aduaneras activas</td></tr>';
      return;
    }

    list.forEach(r => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><strong>${r.codigo_retencion}</strong></td>
        <td>${r.codigo_turno} / ${r.vehiculo_placa}</td>
        <td>${r.contenedor_id}</td>
        <td><span class="block-status-badge status-bloqueado">${r.causa}</span></td>
        <td>${r.estacion}</td>
        <td>Plaza ${r.plaza_numero}</td>
        <td>${r.tiempo_retencion_min} min</td>
        <td>${r.estado}</td>
        <td>
          ${r.estado === 'ABIERTA' ? `
            <button class="btn-cmd" style="padding: 4px 8px; font-size: 11px;" onclick="resolverAduana(${r.id}, 'ACLARAR')">Aclarar</button>
            <button class="btn-cmd danger" style="padding: 4px 8px; font-size: 11px;" onclick="resolverAduana(${r.id}, 'RECHAZAR')">Rechazar</button>
          ` : 'RESUELTA'}
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error('Error retenciones aduaneras:', e);
  }
}

async function resolverAduana(retId, tipo) {
  let motivo = '';
  if (tipo === 'RECHAZAR') {
    motivo = prompt('Indique el motivo obligatorio de rechazo por Aduana:');
    if (!motivo) return;
  }

  try {
    const resp = await fetch(`/api/retenciones/${retId}/resolver`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resolucion: tipo, motivo_rechazo: motivo })
    });
    const data = await resp.json();
    if (resp.ok) {
      alert(`Retención aduanera resuelta mediante ${tipo}`);
      loadRetencionesAduaneras();
    } else {
      alert('Error: ' + data.error);
    }
  } catch (e) {
    alert('Fallo de red: ' + e);
  }
}

function openLevanteModal(manifId, contenedorId) {
  currentResolvingLevanteId = manifId;
  document.getElementById('levanteDetalleBox').innerHTML = `
    <strong>Manifiesto:</strong> ${manifId} | <strong>Contenedor:</strong> ${contenedorId}
  `;
  document.getElementById('groupMotivoRetencion').style.display = 'none';
  openModal('modalResolverLevante');
}

async function submitLevanteDecision(decision) {
  if (!currentResolvingLevanteId) return;

  const canal = document.getElementById('selCanalSelectivo').value;
  const motivo = document.getElementById('inputMotivoRetencion').value.trim();

  if (decision === 'RETENER' && !motivo) {
    document.getElementById('groupMotivoRetencion').style.display = 'block';
    alert('Para retener el levante aduanero es obligatorio indicar el motivo.');
    return;
  }

  try {
    const resp = await fetch('/api/autoridad/resolver-levante', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        manifiesto_id: currentResolvingLevanteId,
        decision: decision,
        canal: canal,
        motivo: motivo
      })
    });
    const data = await resp.json();
    if (resp.ok) {
      alert(data.message);
      closeModal('modalResolverLevante');
      loadAutoridadData();
    } else {
      alert('Error: ' + data.error);
    }
  } catch (err) {
    alert('Fallo de red: ' + err);
  }
}
