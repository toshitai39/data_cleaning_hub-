import Plot from 'react-plotly.js';

const COMMON_LAYOUT = {
  plot_bgcolor: '#ffffff',
  paper_bgcolor: '#ffffff',
  font: { color: '#334155' },
  margin: { l: 60, r: 20, t: 30, b: 80 },
};

export default function PlotlyChart({ data, layout = {}, height = 400, ...rest }) {
  return (
    <Plot
      data={data}
      layout={{ ...COMMON_LAYOUT, height, ...layout }}
      style={{ width: '100%' }}
      config={{ displaylogo: false, responsive: true }}
      useResizeHandler
      {...rest}
    />
  );
}
