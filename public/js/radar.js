/* radar.js · 六维雷达渲染：ECharts CDN → 本地 vendor → 表格（三级降级） */
(function () {
  var CDN = "https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js";
  var LOCAL = "../assets/vendor/echarts.min.js"; // pages/ 下的相对路径

  function loadScript(src, ok, fail) {
    var s = document.createElement("script");
    s.src = src; s.onload = ok; s.onerror = fail;
    document.head.appendChild(s);
  }

  function renderTable(container, dims, baseline, low, high) {
    var rows = dims.map(function (d) {
      return "<tr><td>" + d.name + "</td><td>" + d.score.toFixed(1) + "</td></tr>";
    }).join("");
    container.innerHTML =
      '<table class="dim"><thead><tr><th>维度</th><th>得分</th></tr></thead><tbody>' + rows +
      '</tbody></table><p style="margin-top:10px;font-size:13px;color:var(--c-text-2)">C0 基线 ' +
      baseline.toFixed(2) + " ｜ 七天情景推演区间 " + low.toFixed(2) + " ~ " + high.toFixed(2) +
      "（表格为雷达图降级展示）</p>";
  }

  function renderChart(container, dims, baseline, low, high) {
    var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var option = {
      animation: !reduced,
      animationDuration: 900,
      animationEasing: "cubicOut",
      tooltip: {},
      legend: { bottom: 0, data: ["C0 基线", "七天推演 low", "七天推演 high"],
        textStyle: { color: "#4d5566", fontSize: 12 } },
      radar: {
        indicator: dims.map(function (d) { return { name: d.name, max: 100 }; }),
        radius: "62%",
        axisName: { color: "#4d5566", fontSize: 12.5 },
        splitLine: { lineStyle: { color: "rgba(22,30,52,.10)" } },
        splitArea: { areaStyle: { color: ["#ffffff", "#fafbfc"] } },
        axisLine: { lineStyle: { color: "rgba(22,30,52,.12)" } }
      },
      series: [{
        type: "radar",
        data: [
          { value: dims.map(function (d) { return d.score; }), name: "C0 基线",
            areaStyle: { color: "rgba(47,107,255,.16)" },
            lineStyle: { color: "#2f5fe8", width: 2 }, itemStyle: { color: "#2f5fe8" } },
          { value: dims.map(function (d) { return Math.min(100, d.score * (low / baseline)); }), name: "七天推演 low",
            lineStyle: { color: "#8fabf5", type: "dashed" }, itemStyle: { color: "#8fabf5" } },
          { value: dims.map(function (d) { return Math.min(100, d.score * (high / baseline)); }), name: "七天推演 high",
            lineStyle: { color: "#15803d", type: "dashed" }, itemStyle: { color: "#15803d" } }
        ]
      }]
    };
    var chart = window.echarts.init(container);
    chart.setOption(option);
    window.addEventListener("resize", function () { chart.resize(); });
  }

  // forceTable=true 时直接演示表格降级（degraded 态）
  function mount(containerId, ability, forceTable) {
    var container = document.getElementById(containerId);
    if (!container || !ability) return;
    var dims = ability.dimensions;
    function fallbackTable() { renderTable(container, dims, ability.baseline, ability.scenario_day7.low, ability.scenario_day7.high); }
    function tryChart() { renderChart(container, dims, ability.baseline, ability.scenario_day7.low, ability.scenario_day7.high); }
    if (forceTable) { fallbackTable(); return; }
    if (window.echarts) { tryChart(); return; }
    loadScript(CDN, tryChart, function () {
      loadScript(LOCAL, tryChart, fallbackTable);
    });
  }

  window.RADAR = { mount: mount };
})();
