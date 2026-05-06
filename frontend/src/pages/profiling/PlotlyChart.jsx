import Plot from 'react-plotly.js';

const BASE_LAYOUT = {
  plot_bgcolor: '#ffffff',
  paper_bgcolor: '#ffffff',
  font: { color: '#334155', family: 'Inter, system-ui, sans-serif', size: 12 },
  hoverlabel: { bgcolor: '#1e293b', bordercolor: '#1e293b', font: { color: '#ffffff' } },
  xaxis: { gridcolor: '#f1f5f9', zerolinecolor: '#e2e8f0', automargin: true },
  yaxis: { gridcolor: '#f1f5f9', zerolinecolor: '#e2e8f0', automargin: true },
  legend: {
    orientation: 'h',
    yanchor: 'bottom',
    y: -0.32,
    xanchor: 'center',
    x: 0.5,
    bgcolor: 'rgba(255,255,255,0)',
  },
  margin: { l: 80, r: 24, t: 24, b: 90 },
};

function deepMerge(base, override) {
  if (!override) return base;
  const out = { ...base };
  for (const key of Object.keys(override)) {
    const a = base[key];
    const b = override[key];
    if (a && b && typeof a === 'object' && !Array.isArray(a) && typeof b === 'object' && !Array.isArray(b)) {
      out[key] = deepMerge(a, b);
    } else {
      out[key] = b;
    }
  }
  return out;
}

export default function PlotlyChart({ data, layout = {}, height = 400, ...rest }) {
  const merged = deepMerge(BASE_LAYOUT, layout);
  merged.height = height;
  merged.autosize = true;
  return (
    <Plot
      data={data}
      layout={merged}
      style={{ width: '100%', height: `${height}px` }}
      config={{ displaylogo: false, responsive: true, displayModeBar: false }}
      useResizeHandler
      {...rest}
    />
  );
}
