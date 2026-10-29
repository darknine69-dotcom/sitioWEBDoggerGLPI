(() => {
  const dataNode = document.getElementById('puntoDashboardData');
  if (!dataNode) return;
  let data;
  try { data = JSON.parse(dataNode.textContent); } catch (_) { return; }
  const esc = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const points = values => values.map((value, index) => `${index * (100 / Math.max(values.length - 1, 1))},${44 - (value / Math.max(...values, 1)) * 38}`).join(' ');
  const bindChartDetails = (host, nodes, read) => {
    if (!host || !nodes.length) return;
    let popup = host.querySelector('.pv-chart-tooltip');
    if (!popup) {
      popup = document.createElement('div');
      popup.className = 'pv-chart-tooltip';
      popup.setAttribute('role', 'status');
      popup.innerHTML = '<b></b><span></span><small></small>';
      host.appendChild(popup);
    }
    const position = event => {
      const rect = host.getBoundingClientRect();
      const x = (event && event.clientX ? event.clientX : rect.left + rect.width / 2) - rect.left;
      const y = (event && event.clientY ? event.clientY : rect.top + 24) - rect.top;
      popup.style.left = `${Math.max(8, Math.min(x + 12, rect.width - 172))}px`;
      popup.style.top = `${Math.max(5, Math.min(y - 58, rect.height - 72))}px`;
    };
    const show = (node, event) => {
      const detail = read(node);
      popup.querySelector('b').textContent = detail.title;
      popup.querySelector('span').textContent = detail.value;
      popup.querySelector('small').textContent = detail.meta || '';
      popup.classList.add('is-visible');
      node.classList.add('is-highlighted');
      position(event);
    };
    const hide = node => {
      popup.classList.remove('is-visible');
      node.classList.remove('is-highlighted');
    };
    nodes.forEach(node => {
      node.tabIndex = 0;
      node.addEventListener('pointerenter', event => show(node, event));
      node.addEventListener('pointermove', event => position(event));
      node.addEventListener('pointerleave', () => hide(node));
      node.addEventListener('focus', () => show(node));
      node.addEventListener('blur', () => hide(node));
    });
  };
  document.querySelectorAll('[data-pv-spark]').forEach(node => {
    const item = (data.kpis || []).find(kpi => kpi.key === node.dataset.pvSpark);
    if (!item || !item.serie || !item.serie.some(Boolean)) {
      node.innerHTML = '<span class="pv-spark-empty">Sin datos históricos</span>';
      return;
    }
    const title = item.serie.map((value, index) => `${data.etiquetas[index]}: ${value}`).join('\n');
    node.innerHTML = `<svg viewBox="0 0 100 48" preserveAspectRatio="none" role="img"><title>${esc(title)}</title><polyline points="${points(item.serie)}"></polyline></svg>`;
  });
  const donut = document.querySelector('[data-pv-donut]');
  if (donut) {
    const states = data.estados || {};
    const segments = [
      ['#F59E0B', Number(states.abiertos || 0)],
      ['#84CC16', Number(states.progreso || 0)],
      ['#10B981', Number(states.resueltos || 0)],
      ['#94A3B8', Number(states.cerrados || 0)]
    ];
    const total = Number(data.total || 0);
    let cursor = 0;
    const stops = segments.filter(([, value]) => value > 0).map(([color, value]) => {
      const next = cursor + (value * 100 / total);
      const stop = `${color} ${cursor}% ${next}%`;
      cursor = next;
      return stop;
    });
    donut.style.setProperty('--pv-donut', stops.length ? `conic-gradient(${stops.join(',')})` : 'conic-gradient(#E2E8F0 0 100%)');
    const label = donut.querySelector('strong');
    if (label) label.textContent = String(total);
  }
  const renderBars = (target, rows, color) => {
    if (!target) return;
    if (!rows.length) { target.innerHTML = '<p class="pv-empty">Sin datos para el período seleccionado.</p>'; return; }
    const max = Math.max(...rows.map(row => row.total), 1);
    target.innerHTML = `<div class="pv-bars">${rows.map(row => `<span class="pv-bar-item" data-pv-name="${esc(row.nombre)}" data-pv-total="${row.total}"><i style="height:${Math.max(5, row.total * 100 / max)}%"></i><b>${row.total}</b><small>${esc(row.nombre)}</small></span>`).join('')}</div>`;
    target.querySelectorAll('.pv-bar-item i').forEach(bar => bar.style.background = color);
    bindChartDetails(target, target.querySelectorAll('.pv-bar-item'), node => ({
      title: node.dataset.pvName,
      value: `${node.dataset.pvTotal} solicitudes`,
      meta: `${Math.round(Number(node.dataset.pvTotal) * 100 / rows.reduce((sum, row) => sum + Number(row.total || 0), 0))}% del total mostrado`
    }));
  };
  renderBars(document.querySelector('[data-pv-points]'), data.puntos || [], 'linear-gradient(#60A5FA,#2563EB)');
  const categoryColors = ['#FB4B63', '#2563EB', '#FBBF24', '#67C57A', '#7C4DFF', '#38BDF8'];
  const categories = document.querySelector('[data-pv-category]');
  const renderCategories = rows => {
    if (!categories) return;
    const total = rows.reduce((sum, row) => sum + Number(row.total || 0), 0);
    if (!rows.length || !total) {
      categories.innerHTML = '<p class="pv-empty">Sin categorías registradas para este estado.</p>';
      return;
    }
    let cursor = 0;
    const stops = rows.map((row, index) => {
      const next = cursor + (Number(row.total) * 100 / total);
      const stop = `${categoryColors[index % categoryColors.length]} ${cursor}% ${next}%`;
      cursor = next;
      return stop;
    });
    categories.innerHTML = `<div class="pv-category-chart"><div class="pv-chart-donut" style="background:conic-gradient(${stops.join(',')})"><span><b>${total}</b><small>Solicitudes</small></span></div><div class="pv-category-list">${rows.map((row, index) => `<div class="pv-category-item" data-pv-name="${esc(row.nombre)}" data-pv-total="${row.total}" data-pv-pct="${Math.round(row.total * 100 / total)}"><i style="background:${categoryColors[index % categoryColors.length]}"></i><span>${esc(row.nombre)}</span><b>${row.total}<small>${Math.round(row.total * 100 / total)}%</small></b></div>`).join('')}</div></div>`;
    bindChartDetails(categories, categories.querySelectorAll('.pv-category-item'), node => ({
      title: node.dataset.pvName,
      value: `${node.dataset.pvTotal} solicitudes`,
      meta: `${node.dataset.pvPct}% de las solicitudes por categoría`
    }));
  };
  renderCategories(data.categorias || []);

  const period = document.querySelector('[data-pv-period]');
  const renderPeriod = () => {
    if (!period) return;
    const serie = data.periodo || {};
    const labels = serie.etiquetas || [];
    const lines = [
      { key: 'entrantes', label: 'Entrantes', color: '#2563EB', values: serie.entrantes || [] },
      { key: 'completados', label: 'Completados', color: '#10B981', values: serie.completados || [] },
      { key: 'vencidos', label: 'Vencidos', color: '#FB4B63', values: serie.vencidos || [] }
    ];
    const all = lines.flatMap(line => line.values.map(Number));
    if (!labels.length || !all.some(Boolean)) {
      period.innerHTML = '<p class="pv-empty">Sin datos históricos para el período.</p>';
      return;
    }
    const width = 330, height = 112, top = 12, bottom = 25, max = Math.max(...all, 1);
    const coords = values => values.map((value, i) => [
      12 + i * ((width - 24) / Math.max(values.length - 1, 1)),
      height - bottom - (Number(value) / max) * (height - top - bottom)
    ]);
    const grid = [0, .5, 1].map(step => `<line x1="12" x2="${width - 12}" y1="${height - bottom - step * (height - top - bottom)}" y2="${height - bottom - step * (height - top - bottom)}"/>`).join('');
    const paths = lines.map(line => {
      const ps = coords(line.values);
      return `<polyline class="pv-period-series" style="stroke:${line.color}" points="${ps.map(p => p.join(',')).join(' ')}"></polyline>${ps.map((p, i) => `<circle class="pv-period-point" data-pv-name="${esc(line.label)}" data-pv-label="${esc(labels[i])}" data-pv-total="${line.values[i] || 0}" style="fill:${line.color}" cx="${p[0]}" cy="${p[1]}" r="3"><title>${esc(`${line.label} · ${labels[i]}: ${line.values[i] || 0}`)}</title></circle>`).join('')}`;
    }).join('');
    period.innerHTML = `<div class="pv-period-legend">${lines.map(line => `<span><i style="background:${line.color}"></i>${line.label}</span>`).join('')}</div><svg class="pv-period-line" viewBox="0 0 ${width} ${height}" role="img" aria-label="Solicitudes por período"><g class="pv-period-grid">${grid}</g>${paths}${labels.map((label, i) => `<text x="${12 + i * ((width - 24) / Math.max(labels.length - 1, 1))}" y="${height - 5}" text-anchor="middle">${esc(label)}</text>`).join('')}</svg>`;
    bindChartDetails(period, period.querySelectorAll('.pv-period-point'), node => ({
      title: node.dataset.pvName,
      value: `${node.dataset.pvTotal} solicitudes`,
      meta: `Fecha: ${node.dataset.pvLabel}`
    }));
  };
  renderPeriod();

  document.querySelectorAll('[data-pv-chart-filter]').forEach(select => {
    select.addEventListener('change', () => renderCategories((data.categorias_por_estado || {})[select.value || 'todos'] || []));
  });
  document.querySelectorAll('[data-pv-refresh]').forEach(button => {
    button.addEventListener('click', () => {
      button.classList.add('is-refreshing');
      renderBars(document.querySelector('[data-pv-points]'), data.puntos || [], 'linear-gradient(#60A5FA,#2563EB)');
      renderCategories((data.categorias_por_estado || {}).todos || data.categorias || []);
      renderPeriod();
      window.setTimeout(() => button.classList.remove('is-refreshing'), 300);
    });
  });
})();
