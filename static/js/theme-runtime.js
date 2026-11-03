(function () {
    "use strict";
    var root = document.documentElement;
    var media = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)");
    var themeKey = root.getAttribute("data-theme-storage-key") || "dogger:pv:theme:guest";
    function preference() { try { return localStorage.getItem(themeKey) || "system"; } catch (_) { return "system"; } }
    function systemChange() {
        if (preference() === "system") root.setAttribute("data-theme", media && media.matches ? "dark" : "light");
    }
    if (media) {
        if (media.addEventListener) media.addEventListener("change", systemChange);
        else if (media.addListener) media.addListener(systemChange);
    }
    window.addEventListener("storage", function (event) {
        if (event.key !== themeKey) return;
        var pref = preference();
        root.setAttribute("data-theme", pref === "dark" || pref === "light" ? pref : (media && media.matches ? "dark" : "light"));
    });

    // Chart.js: conservar los colores originales para volver al tema claro.
    var original = new WeakMap();
    function refreshCharts() {
        var Chart = window.Chart;
        if (!Chart || !Chart.instances) return;
        var dark = root.getAttribute("data-theme") === "dark";
        Object.values(Chart.instances).forEach(function (chart) {
            if (!chart || !chart.options) return;
            try {
                var snapshot = original.get(chart);
                if (!snapshot) {
                    snapshot = { scales: {}, legend: undefined };
                    Object.keys(chart.options.scales || {}).forEach(function (key) {
                        var scale = chart.options.scales[key];
                        snapshot.scales[key] = { ticks: scale.ticks && scale.ticks.color, grid: scale.grid && scale.grid.color };
                    });
                    var labels = chart.options.plugins && chart.options.plugins.legend && chart.options.plugins.legend.labels;
                    if (labels) snapshot.legend = labels.color;
                    original.set(chart, snapshot);
                }
                Object.keys(chart.options.scales || {}).forEach(function (key) {
                    var scale = chart.options.scales[key], saved = snapshot.scales[key] || {};
                    if (scale.ticks) scale.ticks.color = dark ? "#bdbdbd" : saved.ticks;
                    if (scale.grid) scale.grid.color = dark ? "rgba(190,190,190,.20)" : saved.grid;
                });
                var legend = chart.options.plugins && chart.options.plugins.legend && chart.options.plugins.legend.labels;
                if (legend) legend.color = dark ? "#d9d9d9" : snapshot.legend;
                chart.update("none");
            } catch (_) { /* Un gráfico específico no debe impedir el cambio de tema. */ }
        });
    }
    new MutationObserver(refreshCharts).observe(root, { attributes: true, attributeFilter: ["data-theme"] });
    document.addEventListener("DOMContentLoaded", refreshCharts);
}());
