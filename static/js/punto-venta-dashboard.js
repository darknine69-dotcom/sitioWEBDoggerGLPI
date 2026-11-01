(() => {
  const dataNode = document.getElementById('puntoDashboardData');
  if (!dataNode) return;
  let data;
  try { data = JSON.parse(dataNode.textContent); } catch (_) { return; }
  const zoneDialog = document.querySelector('.pv-zone-dialog');
  if (zoneDialog) {
    document.querySelectorAll('[data-zone-open]').forEach(button => button.addEventListener('click', () => {
      const zone = (data.ranking || [])[Number(button.dataset.zoneOpen)];
      if (!zone) return;
      ['nombre', 'total', 'abiertos', 'en_progreso', 'resueltos', 'cerrados', 'vencidos'].forEach(key => {
        const selector = { nombre: 'name', en_progreso: 'progreso' }[key] || key;
        const target = zoneDialog.querySelector(`[data-zone-${selector}]`);
        if (target) target.textContent = zone[key] == null ? '—' : String(zone[key]);
      });
      zoneDialog.showModal();
    }));
    zoneDialog.querySelector('[data-zone-close]').addEventListener('click', () => zoneDialog.close());
    zoneDialog.addEventListener('click', event => { if (event.target === zoneDialog) zoneDialog.close(); });
  }
  const esc = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const points = values => values.map((value, index) => `${index * (100 / Math.max(values.length - 1, 1))},${44 - (value / Math.max(...values, 1)) * 38}`).join(' ');
  const segmentOverlay = (donut, values, colors) => {
    const total = values.reduce((sum, n) => sum + n, 0);
    if (!total) return () => {};
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 100 100');
    svg.setAttribute('aria-hidden', 'true');
    svg.classList.add('pv-segment-overlay');
    donut.style.background = 'none';
    let cursor = 0;
    const circumference = 2 * Math.PI * 42;
    const arcs = values.map((value, index) => {
      const start = cursor;
      cursor += value / total;
      const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      circle.setAttribute('cx', '50'); circle.setAttribute('cy', '50'); circle.setAttribute('r', '42');
      circle.setAttribute('fill', 'none'); circle.setAttribute('stroke', colors[index]);
      circle.setAttribute('stroke-width', '16');
      circle.setAttribute('stroke-dasharray', `${value / total * circumference} ${circumference}`);
      circle.setAttribute('stroke-dashoffset', `${-start * circumference}`);
      svg.appendChild(circle);
      return { circle, middle: (start + value / total / 2) * Math.PI * 2 };
    });
    donut.appendChild(svg);
    return index => arcs.forEach((arc, i) => {
      const selected = i === index && values[i] > 0;
      arc.circle.style.transform = selected ? `translate(${Math.cos(arc.middle) * 9}px, ${Math.sin(arc.middle) * 9}px)` : '';
      arc.circle.classList.toggle('is-selected', selected);
      if (selected) svg.appendChild(arc.circle);
    });
  };
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
    const max = Math.max(...item.serie, 1);
    const dots = item.serie.map((value, index) => {
      const x = index * (100 / Math.max(item.serie.length - 1, 1));
      const y = 44 - (value / max) * 38;
      return `<span class="pv-spark-dot" style="left:${x}%;top:${y / 48 * 100}%" data-index="${index}"></span>`;
    }).join('');
    node.innerHTML = `<svg viewBox="0 0 100 48" preserveAspectRatio="none" role="img"><title>${esc(title)}</title><polyline vector-effect="non-scaling-stroke" points="${points(item.serie)}"></polyline></svg>${dots}`;
    bindChartDetails(node, node.querySelectorAll('.pv-spark-dot[data-index]'), dot => {
      const index = Number(dot.dataset.index);
      return {title: data.etiquetas[index] || '', value: `${item.serie[index]} tickets`, meta: item.titulo || ''};
    });
  });
  const donut = document.querySelector('[data-pv-donut]');
  if (donut) {
    const states = data.estados || {};
    const segments = [
      ['#F59E0B', Number(states.abiertos || 0)],
      ['#84CC16', Number(states.progreso || 0)],
      ['#10B981', Number(states.resueltos_estado || 0)],
      ['#94A3B8', Number(states.cerrados_estado || 0)]
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
    const body = donut.closest('.pv-state-body');
    const definitions = [
      { key: 'abierto', name: 'Abiertos', value: Number(states.abiertos || 0) },
      { key: 'progreso', name: 'En progreso', value: Number(states.progreso || 0) },
      { key: 'resuelto', name: 'Resueltos', value: Number(states.resueltos || 0), chartValue: Number(states.resueltos_estado || 0) },
      { key: 'cerrado', name: 'Cerrados', value: Number(states.cerrados || 0), chartValue: Number(states.cerrados_estado || 0) },
      { key: 'vencido', name: 'ANS vencidos', value: Number(states.vencidos || 0) }
    ];
    const highlightState = segmentOverlay(donut, definitions.slice(0, 4).map(item => item.chartValue === undefined ? item.value : item.chartValue), segments.map(segment => segment[0]));
    if (body) {
      const popup = document.createElement('div');
      popup.className = 'pv-chart-tooltip';
      popup.setAttribute('role', 'status');
      popup.innerHTML = '<b></b><span></span><small></small>';
      body.appendChild(popup);
      const showState = (item, event) => {
        if (!item) { popup.classList.remove('is-visible'); return; }
        highlightState(definitions.indexOf(item));
        popup.querySelector('b').textContent = item.name;
        popup.querySelector('span').textContent = `${item.value} ${item.value === 1 ? 'ticket' : 'tickets'}`;
        popup.querySelector('small').textContent = `${total ? Math.round(item.value * 100 / total) : 0}% del total${item.key === 'vencido' ? ' · indicador ANS' : ''}`;
        const rect = body.getBoundingClientRect();
        const x = event && event.clientX ? event.clientX - rect.left : rect.width / 2;
        const y = event && event.clientY ? event.clientY - rect.top : 30;
        popup.style.left = `${Math.max(0, Math.min(x + 12, rect.width - 165))}px`;
        popup.style.top = `${Math.max(0, Math.min(y - 55, rect.height - 70))}px`;
        popup.classList.add('is-visible');
      };
      const hideState = () => { popup.classList.remove('is-visible'); highlightState(-1); };
      body.querySelectorAll('[data-pv-state]').forEach(row => {
        const item = definitions.find(entry => entry.key === row.dataset.pvState);
        row.tabIndex = 0;
        row.addEventListener('pointerenter', event => showState(item, event));
        row.addEventListener('pointermove', event => showState(item, event));
        row.addEventListener('pointerleave', hideState);
        row.addEventListener('focus', () => showState(item));
        row.addEventListener('blur', hideState);
      });
      donut.addEventListener('pointermove', event => {
        const rect = donut.getBoundingClientRect();
        const x = event.clientX - rect.left - rect.width / 2;
        const y = event.clientY - rect.top - rect.height / 2;
        const distance = Math.hypot(x, y);
        const outer = rect.width / 2;
        if (!total || distance > outer || distance < outer - 19) { hideState(); return; }
        const fraction = ((Math.atan2(x, -y) / (2 * Math.PI)) + 1) % 1;
        let accumulated = 0;
        const item = definitions.slice(0, 4).find(entry => {
          const chartValue = entry.chartValue === undefined ? entry.value : entry.chartValue;
          accumulated += chartValue / total;
          return chartValue > 0 && fraction < accumulated;
        });
        showState(item, event);
      });
      donut.addEventListener('pointerleave', hideState);
    }
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
    const categoryDonut = categories.querySelector('.pv-chart-donut');
    const categoryItems = [...categories.querySelectorAll('.pv-category-item')];
    const highlightCategory = segmentOverlay(categoryDonut, rows.map(row => Number(row.total || 0)), rows.map((_, index) => categoryColors[index % categoryColors.length]));
    categoryItems.forEach((item, index) => {
      item.addEventListener('pointerenter', () => highlightCategory(index));
      item.addEventListener('pointerleave', () => highlightCategory(-1));
      item.addEventListener('focus', () => highlightCategory(index));
      item.addEventListener('blur', () => highlightCategory(-1));
    });
    categoryDonut.addEventListener('pointermove', event => {
      const rect = categoryDonut.getBoundingClientRect();
      const x = event.clientX - rect.left - rect.width / 2;
      const y = event.clientY - rect.top - rect.height / 2;
      const distance = Math.hypot(x, y);
      if (distance > rect.width / 2 || distance < rect.width * .32) { highlightCategory(-1); return; }
      const fraction = ((Math.atan2(x, -y) / (2 * Math.PI)) + 1) % 1;
      let cumulative = 0;
      const index = rows.findIndex(row => { cumulative += Number(row.total) / total; return fraction < cumulative; });
      highlightCategory(index);
    });
    categoryDonut.addEventListener('pointerleave', () => highlightCategory(-1));
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
