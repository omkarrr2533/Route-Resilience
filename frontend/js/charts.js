// The robustness panel: largest-connected-component size as edges are removed, targeted vs
// random. One Chart.js line chart, themed down to match the console. The visual point is the
// gap between the two lines — drawn filled so it reads as "the fragility envelope".
const RobustChart = (() => {
  let chart;

  const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

  function render(canvasId, data) {
    const ctx = document.getElementById(canvasId).getContext("2d");
    const critical = css("--critical") || "#ff4d5e";
    const cyan = css("--accent-2") || "#36d6c3";
    const faint = "rgba(173,201,204,0.10)";

    const series = (curve) => curve.fractions.map((x, i) => ({ x, y: curve.lcc[i] }));

    if (chart) chart.destroy();
    chart = new Chart(ctx, {
      type: "line",
      data: {
        datasets: [
          dataset("targeted", series(data.targeted), critical, true),
          dataset("random", series(data.random), cyan, false),
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        animation: { duration: 600 },
        interaction: { mode: "index", intersect: false },
        scales: {
          x: { type: "linear", min: 0, max: 1, grid: { color: faint },
               ticks: tick("fraction removed"), border: { color: faint } },
          y: { min: 0, max: 1, grid: { color: faint },
               ticks: tick("LCC"), border: { color: faint } },
        },
        plugins: {
          legend: { display: false },
          tooltip: { backgroundColor: "#0e1315", borderColor: faint, borderWidth: 1,
                     titleFont: { family: "IBM Plex Mono", size: 10 },
                     bodyFont: { family: "IBM Plex Mono", size: 11 } },
        },
      },
    });
  }

  function dataset(label, data, color, fill) {
    return {
      label, data, borderColor: color,
      backgroundColor: fill ? color + "22" : "transparent",
      fill: fill ? "+1" : false,           // shade the gap down to the random curve
      tension: 0.25, borderWidth: 2,
      pointRadius: 0, pointHoverRadius: 4, pointHoverBackgroundColor: color,
    };
  }

  function tick(title) {
    return {
      color: "#5b6469", font: { family: "IBM Plex Mono", size: 9 },
      maxTicksLimit: 5, callback: v => v,
    };
  }

  return { render };
})();
