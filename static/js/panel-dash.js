/* Panel Técnico · Dashboard v2 (pivote + gráficos Chart.js) */
(function () {
    'use strict';
    var NS = 'http://www.w3.org/2000/svg';

    var dataEl = document.getElementById('dashData');
    if (!dataEl) return;
    var D = null;
    try { D = JSON.parse(dataEl.textContent); } catch (e) { console.error('dashData inválido', e); }
    if (!D || !D.pivot) return;

    var SERIE = D.colores_serie || {
        entrante: '#2563EB', completado: '#2F7D4F', vencido: '#D62B1F', riesgo: '#F2A900'
    };
    var PAL = ['#2563EB', '#2F7D4F', '#F2A900', '#B7791F', '#8A8A86', '#6B6259', '#D62B1F'];
    var COLS = { abrir: 'Abrir', espera: 'En Espera', vencido: 'Vencido', total: 'Total' };

    Chart.register({
        id: 'valorBarras',
        afterDatasetsDraw: function (chart) {
            if (chart.config.type !== 'bar') return;
            var stacked = chart.options.scales && chart.options.scales.y && chart.options.scales.y.stacked;
            var ctx = chart.ctx;
            chart.data.datasets.forEach(function (ds, di) {
                if (stacked && di > 0) return;
                var meta = chart.getDatasetMeta(di);
                meta.data.forEach(function (el, i) {
                    var v = ds.data[i];
                    if (!v) return;
                    ctx.save();
                    ctx.fillStyle = '#6B6259';
                    ctx.font = 'bold 11px sans-serif';
                    ctx.textAlign = 'center';
                    ctx.fillText(v, el.x, (stacked ? el.y : el.base) - 5);
                    ctx.restore();
                });
            });
        }
    });

    var TIPOS = ['bar', 'line', 'area', 'pie', 'donut', 'funnel', 'pyramid', 'count'];
    var TIPO_LABEL = {
        bar: 'Barras', line: 'Línea', area: 'Área', pie: 'Circular',
        donut: 'Dona', funnel: 'Embudo', pyramid: 'Pirámide', count: 'Recuento'
    };
    var DEFAULT_TIPO = { modo: 'pie', categoria: 'pie', prioridad: 'pie', linea: 'line', sla: 'bar', comp20: 'bar' };
    var estado = {};

    var charts = {};
    // ------------------------------------------------------------------
    // Datos por widget
    // ------------------------------------------------------------------
    function serieWidget(w) {
        if (w === 'modo') return { pairs: D.pie_modo || [] };
        if (w === 'categoria') return { pairs: D.pie_categoria || [] };
        if (w === 'prioridad') return { pairs: D.pie_prioridad || [] };
        if (w === 'linea') {
            var rango = document.getElementById('wLineaRange');
            var d = D.linea[(rango && rango.value) || 'ultima_semana'];
            return {
                labels: d.labels,
                datasets: [
                    { key: 'entrante', label: 'Entrante', data: d.entrante, color: SERIE.entrante },
                    { key: 'completado', label: 'Completado', data: d.completado, color: SERIE.completado },
                    { key: 'vencido', label: 'Vencido', data: d.vencido, color: SERIE.vencido }
                ]
            };
        }
        if (w === 'sla') {
            var dim = document.getElementById('wSlaDim');
            var data = D.sla[(dim && dim.value) || 'por_tecnico'] || [];
            return {
                labels: data.map(function (r) { return r.label; }),
                datasets: [
                    { key: 'vencidos', label: 'Sanción', data: data.map(function (r) { return r.vencidos; }), color: SERIE.vencido },
                    { key: 'riesgo', label: 'Advertencia', data: data.map(function (r) { return r.riesgo; }), color: SERIE.riesgo }
                ]
            };
        }
        if (w === 'comp20') {
            var sel20 = document.getElementById('wComp20');
            var c20 = D.comparativo[(sel20 && sel20.value) || 'recibidas'] || D.comparativo.recibidas;
            return {
                labels: c20.labels,
                datasets: [
                    { key: 'ok', label: 'Sin infracción', data: c20.ok, color: '#2F7D4F' },
                    { key: 'brecha', label: 'Con infracción', data: c20.brecha, color: SERIE.vencido }
                ]
            };
        }
        var c = D.comparativo[w === 'recibidas' ? 'recibidas' : 'completadas'];
        return {
            labels: c.labels,
            datasets: [
                { key: 'ok', label: 'Sin infracción', data: c.ok, color: '#2F7D4F' },
                { key: 'brecha', label: 'Con infracción', data: c.brecha, color: SERIE.vencido }
            ]
        };
    }

    function pairs(widget) {
        var s = serieWidget(widget);
        if (widget === 'modo' || widget === 'categoria' || widget === 'prioridad') return s.pairs;
        return s.labels.map(function (l, i) {
            var v, color;
            if (widget === 'linea') {
                v = s.datasets[0].data[i];
                color = PAL[i % PAL.length];
            } else if (widget === 'sla') {
                v = s.datasets[0].data[i] + s.datasets[1].data[i];
                color = s.datasets[0].data[i] > 0 ? SERIE.vencido : SERIE.riesgo;
            } else {
                v = s.datasets[0].data[i] + s.datasets[1].data[i];
                color = s.datasets[1].data[i] > 0 ? SERIE.vencido : '#2F7D4F';
            }
            return { label: l, value: v, color: color };
        });
    }

    function countTitle(widget) {
        if (widget === 'modo') return 'solicitudes abiertas por modo';
        if (widget === 'categoria') return 'solicitudes abiertas por categoría';
        if (widget === 'prioridad') return 'solicitudes abiertas por prioridad';
        if (widget === 'linea') return 'entrantes en el período';
        if (widget === 'sla') return 'sanciones por vencimiento de ANS';
        if (widget === 'comp20') {
            var sel20 = document.getElementById('wComp20');
            return (sel20 && sel20.value === 'completadas')
                ? 'completadas en los últimos 20 días'
                : 'recibidas en los últimos 20 días';
        }
        return 'solicitudes en los últimos 20 días';
    }
    // ------------------------------------------------------------------
    // Renderers
    // ------------------------------------------------------------------
    function clearStage(stage) {
        stage.innerHTML = '';
    }

    function renderCount(stage, widget) {
        var tot = pairs(widget).reduce(function (s, p) { return s + p.value; }, 0);
        stage.appendChild(domEl('<div class="chart-count"><strong>' + tot + '</strong><small>' + countTitle(widget) + '</small></div>'));
    }

    function drawFunnelLike(stage, widget, pyramid) {
        var prs = pairs(widget).filter(function (p) { return p.value > 0; });
        if (!prs.length) { stage.appendChild(domEl('<p class="chart-empty">Sin datos.</p>')); return; }
        var max = Math.max.apply(null, prs.map(function (p) { return p.value; })) || 1;
        var W = 620, H = 260, top = 18, base = 330, n = prs.length;
        var step = (H - top * 2) / n;
        var svg = document.createElementNS(NS, 'svg');
        svg.setAttribute('class', 'funnel');
        svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
        prs.forEach(function (p, i) {
            var f = p.value / max;
            var fw = pyramid ? (i + 1) / n : (n - i) / n;
            var w = Math.max(14, 60 + f * base * fw);
            var x = (W - w) / 2;
            var y = top + i * step;
            var hh = Math.max(10, step - 6);
            var r = document.createElementNS(NS, 'rect');
            r.setAttribute('x', x); r.setAttribute('y', y);
            r.setAttribute('width', w); r.setAttribute('height', hh);
            r.setAttribute('rx', 6); r.setAttribute('fill', p.color);
            svg.appendChild(r);
            var t = document.createElementNS(NS, 'text');
            t.setAttribute('x', W / 2); t.setAttribute('y', y + hh / 2 + 4);
            t.setAttribute('text-anchor', 'middle'); t.setAttribute('fill', '#fff');
            t.setAttribute('font-size', '12'); t.setAttribute('font-weight', 'bold');
            t.textContent = p.value;
            svg.appendChild(t);
            var lb = document.createElementNS(NS, 'text');
            lb.setAttribute('x', x - 10); lb.setAttribute('y', y + hh / 2 + 4);
            lb.setAttribute('text-anchor', 'end'); lb.setAttribute('fill', '#6B6259');
            lb.setAttribute('font-size', '11');
            lb.textContent = p.label.length > 24 ? p.label.slice(0, 23) + '…' : p.label;
            svg.appendChild(lb);
        });
        stage.appendChild(svg);
    }

    function tooltipPct(item) {
        var v = (typeof item.parsed === 'object') ? item.parsed.y : item.parsed;
        v = (typeof v === 'number') ? v : 0;
        var total = 0;
        item.chart.data.datasets.forEach(function (ds) {
            ds.data.forEach(function (d) { var n = (typeof d === 'number') ? d : 0; total += n; });
        });
        var name = (item.dataset && item.dataset.label) ? item.dataset.label : item.label;
        var pct = total ? Math.round(v / total * 100) : 0;
        return ' ' + name + ': ' + v + (pct ? ' (' + pct + '%)' : '');
    }

    function configFor(widget, tipo) {
        var multi = serieWidget(widget);
        function single() {
            var prs = pairs(widget);
            return {
                labels: prs.map(function (p) { return p.label; }),
                datasets: [{
                    data: prs.map(function (p) { return p.value; }),
                    backgroundColor: prs.map(function (p) { return p.color; }),
                    borderColor: '#fff', borderWidth: 2, hoverOffset: 20, borderRadius: 4
                }]
            };
        }
        function multiDatasets(stacked) {
            return {
                labels: multi.labels,
                datasets: multi.datasets.map(function (ds) {
                    return {
                        label: ds.label,
                        data: ds.data,
                        backgroundColor: ds.color,
                        borderColor: ds.color,
                        borderWidth: tipo === 'bar' ? 1 : 2,
                        borderRadius: 4,
                        stack: stacked ? 's' : undefined,
                        fill: tipo === 'area' ? 'origin' : false,
                        tension: 0.35,
                        pointRadius: 3,
                        pointHoverRadius: 5,
                        pointBackgroundColor: ds.color
                    };
                })
            };
        }

        var data, opts;
        var scalesX = { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 14 } };
        var scalesY = { beginAtZero: true, ticks: { precision: 0 } };
        var hasMulti = widget === 'linea' || widget === 'sla' || widget === 'comp20' || widget === 'recibidas' || widget === 'completadas';

        if (tipo === 'bar' || tipo === 'line' || tipo === 'area') {
            var stacked = false;
            if ((widget === 'comp20' || widget === 'recibidas' || widget === 'completadas') && tipo === 'bar') stacked = true;
            if (hasMulti) {
                data = multiDatasets(stacked);
            } else {
                var prs = pairs(widget);
                data = {
                    labels: prs.map(function (p) { return p.label; }),
                    datasets: [{
                        label: undefined,
                        data: prs.map(function (p) { return p.value; }),
                        backgroundColor: prs.map(function (p) { return p.color; }),
                        borderColor: prs.map(function (p) { return p.color; }),
                        borderWidth: 1, borderRadius: 4,
                        fill: tipo === 'area' ? 'origin' : false,
                        tension: 0.35,
                        pointRadius: 3, pointHoverRadius: 5,
                        pointBackgroundColor: prs.map(function (p) { return p.color; })
                    }]
                };
            }
            var scales = tipo === 'bar'
                ? { x: stacked ? { stacked: true } : scalesX, y: stacked ? { stacked: true, beginAtZero: true, ticks: { precision: 0 } } : scalesY }
                : { x: scalesX, y: scalesY };
            opts = {
                responsive: true, maintainAspectRatio: false,
                scales: scales,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function (it) {
                                if (it.parsed.y !== undefined) {
                                    var nombre = (it.dataset && it.dataset.label) ? it.dataset.label : it.label;
                                    return ' ' + nombre + ': ' + it.parsed.y;
                                }
                                return tooltipPct(it);
                            }
                        }
                    }
                }
            };
        } else {
            data = single();
            opts = {
                responsive: true, maintainAspectRatio: false, cutout: tipo === 'donut' ? '58%' : 0,
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: tooltipPct } }
                }
            };
        }
        var chartType = tipo === 'area' ? 'line' : (tipo === 'donut' ? 'doughnut' : tipo);
        return { type: chartType, data: data, options: opts };
    }

    function domEl(html) {
        var t = document.createElement('template');
        t.innerHTML = html.trim();
        return t.content.firstChild;
    }

    function render(card, widget) {
        var stage = card.querySelector('[data-stage]');
        function onPie(on) {
            var leg = card.querySelector('[data-pie-legend]');
            if (leg) leg.style.display = on ? '' : 'none';
        }
        var tipo = estado[widget] || DEFAULT_TIPO[widget];
        clearStage(stage);
        if (charts[widget]) { charts[widget].destroy(); charts[widget] = null; }

        if (tipo === 'count') { renderCount(stage, widget); onPie(false); return; }
        if (tipo === 'funnel') { drawFunnelLike(stage, widget, false); onPie(false); return; }
        if (tipo === 'pyramid') { drawFunnelLike(stage, widget, true); onPie(false); return; }

        var canvas = document.createElement('canvas');
        stage.appendChild(canvas);
        var cfg = configFor(widget, tipo);
        var chart = new Chart(canvas.getContext('2d'), cfg);
        var ct = cfg.type || tipo;

        if (ct === 'pie' || ct === 'doughnut') { onPie(true); bindPieCard(card, widget, chart); }
        else onPie(false);
        charts[widget] = chart;
    }

    function bindPieCard(card, widget, chart) {
        var leg = card.querySelector('[data-pie-legend]');
        if (!leg) return;
        var lis = Array.prototype.slice.call(leg.querySelectorAll('li'));
        function setHi(i) {
            try {
                chart.setActiveElements(i >= 0 ? [{ datasetIndex: 0, index: i }] : []);
                chart.update();
            } catch (e) {}
            lis.forEach(function (li, k) { li.classList.toggle('is-hi', k === i); });
        }
        lis.forEach(function (li, i) {
            li.addEventListener('mouseenter', function () { setHi(i); });
            li.addEventListener('mouseleave', function () { setHi(-1); });
        });
        chart.options.onHover = function (ev, items) { setHi(items.length ? items[0].index : -1); };
    }

    // ------------------------------------------------------------------
    // Menú de cambio de tipo
    // ------------------------------------------------------------------
    function prevSvg(tipo) {
        var s = 'stroke="#212121" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"';
        if (tipo === 'bar') return '<svg viewBox="0 0 20 14" class="csm-prev"><rect x="2" y="6" width="3.4" height="6" rx="1" fill="#212121"/><rect x="8.3" y="3" width="3.4" height="9" rx="1" fill="#212121"/><rect x="14.6" y="9" width="3.4" height="3" rx="1" fill="#212121"/></svg>';
        if (tipo === 'line') return '<svg viewBox="0 0 20 14" class="csm-prev"><polyline points="1,12 6,8 10,10 15,4 19,2" ' + s + '/></svg>';
        if (tipo === 'area') return '<svg viewBox="0 0 20 14" class="csm-prev"><path d="M1,12 L6,8 L10,10 L15,4 L19,2 L19,12 Z" fill="#212121" opacity=".25"/><polyline points="1,12 6,8 10,10 15,4 19,2" ' + s + '/></svg>';
        if (tipo === 'donut') return '<svg viewBox="0 0 20 14" class="csm-prev"><circle cx="10" cy="7" r="5.4" ' + s + ' stroke-dasharray="3 2.2 3.4 1.4"/><circle cx="10" cy="7" r="2" ' + s + '/></svg>';
        if (tipo === 'pie') return '<svg viewBox="0 0 20 14" class="csm-prev"><path d="M10 7 L10 1.8 A5.2 5.2 0 0 1 14.6 4.2 Z" fill="#212121"/><path d="M10 7 L14.6 4.2 A5.2 5.2 0 0 1 13 11.6 Z" fill="#212121" opacity=".55"/><path d="M10 7 L13 11.6 A5.2 5.2 0 0 1 6.6 11.8 Z" fill="#212121" opacity=".3"/></svg>';
        if (tipo === 'funnel') return '<svg viewBox="0 0 20 14" class="csm-prev"><path d="M4 1 H16 L13 6 H7 Z" fill="#212121" opacity=".9"/><path d="M6.4 7 H13.6 L12 12 H8 Z" fill="#212121" opacity=".5"/></svg>';
        if (tipo === 'pyramid') return '<svg viewBox="0 0 20 14" class="csm-prev"><path d="M7 1 H13 L15 6 H5 Z" fill="#212121" opacity=".45"/><path d="M5.6 7 H14.4 L16 12 H4 Z" fill="#212121" opacity=".85"/></svg>';
        return '<svg viewBox="0 0 20 14" class="csm-prev"><text x="10" y="11" text-anchor="middle" font-size="9" font-weight="bold" fill="#212121">123</text></svg>';
    }

    function buildMenu(card, widget) {
        var wrap = card.querySelector('[data-switch]');
        if (!wrap) return;
        var btn = domEl('<button type="button" class="chart-switch-btn" data-toggle><svg class="icon icon-sm"><use href="#i-chart"/></svg> Tipo</button>');
        var menu = domEl('<div class="chart-switch-menu" hidden></div>');
        TIPOS.forEach(function (tp) {
            var b = domEl('<button type="button" data-type="' + tp + '">' + prevSvg(tp) + '<span>' + TIPO_LABEL[tp] + '</span></button>');
            b.addEventListener('click', function () {
                estado[widget] = tp;
                markActive();
                menu.hidden = true;
                wrap.removeAttribute('data-open');
                render(card, widget);
            });
            menu.appendChild(b);
        });
        wrap.appendChild(btn);
        wrap.appendChild(menu);
        function markActive() {
            var cur = estado[widget] || DEFAULT_TIPO[widget];
            Array.prototype.forEach.call(menu.querySelectorAll('button[data-type]'), function (b) {
                b.classList.toggle('is-active', b.dataset.type === cur);
            });
        }
        markActive();
        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            var open = !wrap.hasAttribute('data-open');
            TIPOS.forEach(function () {});
            document.querySelectorAll('.chart-switch-menu').forEach(function (m) { m.hidden = true; });
            Array.prototype.forEach.call(document.querySelectorAll('[data-switch]'), function (el) { el.removeAttribute('data-open'); });
            if (open) { wrap.setAttribute('data-open', ''); menu.hidden = false; }
        });
    }
    document.addEventListener('click', function (e) {
        if (!e.target.closest('.chart-switch')) {
            document.querySelectorAll('.chart-switch-menu').forEach(function (m) { m.hidden = true; });
            Array.prototype.forEach.call(document.querySelectorAll('[data-switch]'), function (el) { el.removeAttribute('data-open'); });
        }
    });

    // ------------------------------------------------------------------
    // Tabla dinámica pivote
    // ------------------------------------------------------------------
    function renderPivot(dim) {
        var meta = D.pivot.dimensiones[dim];
        var body = document.getElementById('pivotBody');
        document.getElementById('pivotCol1').textContent = meta.label;
        document.getElementById('pivotDimLabel').textContent = meta.label.toLowerCase();
        var rows = meta.rows.filter(function (r) { return r.total > 0 || r.vencido > 0; });
        var pop0 = document.getElementById('pivotPop');
        if (pop0) pop0.remove();
        if (!rows.length) {
            body.innerHTML = '<tr class="table-empty"><td colspan="5">Sin datos todavía.</td></tr>';
            return;
        }
        var tot = { label: 'Total', abrir: 0, espera: 0, vencido: 0, total: 0, totalRow: true };
        rows.forEach(function (r) {
            tot.abrir += r.abrir; tot.espera += r.espera; tot.vencido += r.vencido; tot.total += r.total;
        });
        var html = rows.map(function (r) {
            return '<tr>' +
                '<td class="pivot-lead">' + esc(r.label) + '</td>' +
                '<td class="num">' + r.abrir + '</td>' +
                '<td class="num">' + r.espera + '</td>' +
                '<td class="num col-vencido">' + (r.vencido ? '<span class="badge-vencido">' + r.vencido + '</span>' : '—') + '</td>' +
                '<td class="num"><strong>' + r.total + '</strong></td>' +
                '</tr>';
        }).join('');
        html += '<tr class="pivot-total-row"><td>' + esc(tot.label) + '</td><td class="num">' + tot.abrir + '</td><td class="num">' + tot.espera + '</td><td class="num col-vencido">' + (tot.vencido ? '<span class="badge-vencido">' + tot.vencido + '</span>' : '—') + '</td><td class="num"><strong>' + tot.total + '</strong></td></tr>';
        body.innerHTML = html;
        Array.prototype.forEach.call(body.querySelectorAll('.pivot-lead'), function (cell, i) {
            cell.addEventListener('click', function (e) {
                e.stopPropagation();
                if (!rows[i]) return;
                showPivotPop(rows[i], cell);
            });
        });
    }

    function showPivotPop(r, anchor) {
        var card = document.querySelector('[data-pivot-card]');
        if (!card) return;
        var vieja = document.getElementById('pivotPop');
        if (vieja) vieja.remove();
        var pop = domEl('<div class="pivot-pop" id="pivotPop"></div>');
        var pct = r.total ? Math.round(r.vencido / r.total * 100) : 0;
        pop.innerHTML =
            '<div class="pivot-pop-head"><strong>' + esc(r.label) + '</strong><button type="button" class="pivot-pop-close" title="Cerrar">&times;</button></div>' +
            '<div class="pivot-pop-stats">' +
            statPiv('Abierto', r.abrir, '#2563EB') +
            statPiv('En espera', r.espera, '#B7791F') +
            statPiv('Vencido', r.vencido, '#D62B1F') +
            statPiv('Total', r.total, '#212121') +
            '</div>' +
            '<div class="pivot-pop-bar">' +
            segPiv(r.abrir, r.total, '#2563EB') +
            segPiv(r.espera, r.total, '#B7791F') +
            segPiv(r.vencido, r.total, '#D62B1F') +
            '</div>' +
            '<div class="pivot-pop-foot">' + pct + '% de sus solicitudes vencidas</div>';
        card.appendChild(pop);
        var cardRect = card.getBoundingClientRect();
        var acr = anchor.getBoundingClientRect();
        pop.style.visibility = 'hidden';
        var w = pop.offsetWidth;
        var h = pop.offsetHeight;
        var x = acr.left - cardRect.left + 8;
        var y = acr.top - cardRect.top + acr.height + 6;
        x = Math.max(6, Math.min(x, cardRect.width - w - 6));
        if (y + h > cardRect.height - 6 && y - h - 10 > 0) y = acr.top - cardRect.top - h - 6;
        pop.style.left = x + 'px';
        pop.style.top = y + 'px';
        pop.style.visibility = '';
        requestAnimationFrame(function () { pop.classList.add('is-in'); });
        pop.querySelector('.pivot-pop-close').addEventListener('click', function (e) {
            e.stopPropagation();
            pop.remove();
        });
    }

    function statPiv(n, v, c) {
        return '<div class="pivot-pop-stat"><span class="pivot-pop-dot" style="background:' + c + '"></span>' + n + '<strong>' + v + '</strong></div>';
    }
    function segPiv(v, total, c) {
        if (!v || !total) return '';
        return '<span style="width:' + (v / total * 100) + '%;background:' + c + '"></span>';
    }

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    // ------------------------------------------------------------------
    // Leyenda de pies (según datos)
    // ------------------------------------------------------------------
    function buildPieLegends() {
        ['modo', 'categoria', 'prioridad'].forEach(function (widget) {
            var card = document.querySelector('.chart-modal[data-widget="' + widget + '"]');
            if (!card) return;
            var leg = card.querySelector('[data-pie-legend]');
            if (!leg) return;
            var prs = pairs(widget);
            var total = prs.reduce(function (s, p) { return s + p.value; }, 0);
            leg.innerHTML = prs.map(function (p) {
                var pct = total ? Math.round(p.value / total * 100) : 0;
                return '<li><span class="pl-dot" style="background:' + p.color + '"></span>' +
                    esc(p.label) +
                    '<span class="pl-val">' + p.value + '</span>' +
                    '<span class="pl-pct">' + pct + '%</span></li>';
            }).join('');
            if (!prs.length) leg.innerHTML = '<li class="chart-empty" style="border:0">Sin datos.</li>';
        });
    }

    // ------------------------------------------------------------------
    // Init
    // ------------------------------------------------------------------
    function init() {
        var pivotSel = document.getElementById('pivotDim');
        if (pivotSel) {
            renderPivot(pivotSel.value);
            pivotSel.addEventListener('change', function () { renderPivot(pivotSel.value); });
        }
        buildPieLegends();
        Array.prototype.forEach.call(document.querySelectorAll('.chart-modal'), function (card) {
            var widget = card.dataset.widget;
            estado[widget] = DEFAULT_TIPO[widget] || 'bar';
            buildMenu(card, widget);
            render(card, widget);
        });
        var range = document.getElementById('wLineaRange');
        if (range) range.addEventListener('change', function () {
            var card = document.querySelector('[data-widget="linea"]');
            if (card) render(card, 'linea');
        });
        var dim = document.getElementById('wSlaDim');
        if (dim) dim.addEventListener('change', function () {
            var card = document.querySelector('[data-widget="sla"]');
            if (card) render(card, 'sla');
        });
        var comp20 = document.getElementById('wComp20');
        if (comp20) comp20.addEventListener('change', function () {
            var lb = document.getElementById('comp20Label');
            if (lb) lb.textContent = comp20.options[comp20.selectedIndex].textContent;
            var card = document.querySelector('[data-widget="comp20"]');
            if (card) render(card, 'comp20');
        });
        document.addEventListener('click', function () {
            var p = document.getElementById('pivotPop');
            if (p) p.remove();
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();