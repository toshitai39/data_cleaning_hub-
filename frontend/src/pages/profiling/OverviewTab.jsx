import { useEffect, useMemo, useState } from 'react';
import {
  Box, Grid, Typography, LinearProgress, Alert, RadioGroup, FormControlLabel, Radio, Stack,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper, Chip,
} from '@mui/material';
import api from '../../api.js';
import PlotlyChart from './PlotlyChart.jsx';
import { sectionHeaderSx } from './sectionStyles.js';

const BLUE_SCALE = [[0, '#dbeafe'], [0.33, '#93c5fd'], [0.66, '#3b82f6'], [1, '#1e40af']];
const RISK_BG = { Low: '#d1fae5', Medium: '#fef3c7', High: '#fecaca' };
const RISK_FG = { Low: '#065f46', Medium: '#92400e', High: '#991b1b' };

export default function OverviewTab() {
  const [data, setData] = useState(null);
  const [corr, setCorr] = useState(null);
  const [corrMethod, setCorrMethod] = useState('pearson');
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.get('/profile/overview'),
      api.get('/profile/correlation', { params: { method: corrMethod } }),
    ])
      .then(([o, c]) => { setData(o.data); setCorr(c.data); })
      .catch((e) => setErr(e?.response?.data?.detail || 'Failed'))
      .finally(() => setLoading(false));
  }, [corrMethod]);

  const detail = data?.detail_table || [];

  // ─── Chart 1: Non-Null Count by Column (horizontal bar) ─────────────
  const chart1 = useMemo(() => {
    if (!data) return null;
    const rows = data.non_null_sorted;
    return {
      data: [{
        type: 'bar',
        orientation: 'h',
        x: rows.map((r) => r['Non-Null Count']),
        y: rows.map((r) => r['Column Name']),
        marker: {
          color: rows.map((r) => r['Non-Null Count']),
          colorscale: BLUE_SCALE,
          showscale: false,
        },
      }],
      layout: { showlegend: false },
    };
  }, [data]);

  // ─── Chart 2: Non-Null vs Null stacked ──────────────────────────────
  const chart2 = useMemo(() => {
    if (!data) return null;
    const rows = data.stack_15;
    return {
      data: [
        { type: 'bar', orientation: 'h', name: 'Non-Null',
          y: rows.map((r) => r['Column Name']), x: rows.map((r) => r['Non-Null Count']),
          marker: { color: '#6366f1' } },
        { type: 'bar', orientation: 'h', name: 'Null',
          y: rows.map((r) => r['Column Name']), x: rows.map((r) => r['Null Count']),
          marker: { color: '#ef4444' } },
      ],
      layout: { barmode: 'stack' },
    };
  }, [data]);

  // ─── Chart 3: Unique Count Distribution ─────────────────────────────
  const chart3 = useMemo(() => {
    if (!data) return null;
    const rows = data.unique_top15;
    return {
      data: [{
        type: 'bar',
        x: rows.map((r) => r['Column Name']),
        y: rows.map((r) => r['Unique Count']),
        marker: {
          color: rows.map((r) => r['Unique Count']),
          colorscale: BLUE_SCALE,
          showscale: false,
        },
      }],
      layout: { showlegend: false, xaxis: { tickangle: -45 } },
    };
  }, [data]);

  // ─── Chart 4: Unique vs Duplicate stacked ───────────────────────────
  const chart4 = useMemo(() => {
    if (!data) return null;
    const rows = data.unique_vs_dup_15;
    return {
      data: [
        { type: 'bar', name: 'Unique',
          x: rows.map((r) => r['Column Name']),
          y: rows.map((r) => r['Unique Count']),
          marker: { color: '#10b981' } },
        { type: 'bar', name: 'Duplicate',
          x: rows.map((r) => r['Column Name']),
          y: rows.map((r) => r['Duplicate Count']),
          marker: { color: '#f59e0b' } },
      ],
      layout: { barmode: 'stack', xaxis: { tickangle: -45 } },
    };
  }, [data]);

  // ─── Chart 5: Risk Score Trend ──────────────────────────────────────
  const chart5 = useMemo(() => {
    if (!data) return null;
    const rows = data.risk_trend;
    return {
      data: [{
        type: 'scatter', mode: 'lines+markers',
        x: rows.map((r) => r['Column Name']),
        y: rows.map((r) => r['Risk Score']),
        line: { shape: 'spline', color: '#3b82f6' },
        marker: { size: 8, color: '#3b82f6', line: { width: 2, color: '#1e40af' } },
      }],
      layout: { xaxis: { tickangle: -45 } },
    };
  }, [data]);

  // ─── Chart 6: Null Percentage Area ──────────────────────────────────
  const chart6 = useMemo(() => {
    if (!data) return null;
    const rows = data.null_pct_trend;
    return {
      data: [{
        type: 'scatter', mode: 'lines',
        x: rows.map((r) => r['Column Name']),
        y: rows.map((r) => r['Null Percentage']),
        fill: 'tozeroy',
        line: { shape: 'spline', color: '#ef4444' },
        fillcolor: 'rgba(239, 68, 68, 0.12)',
      }],
      layout: { xaxis: { tickangle: -45 } },
    };
  }, [data]);

  // ─── Chart 7: Unique% vs Null% bubble ───────────────────────────────
  const chart7 = useMemo(() => {
    if (!data) return null;
    const rows = data.scatter_unique_null;
    return {
      data: [{
        type: 'scatter', mode: 'markers',
        x: rows.map((r) => r['Unique Percentage']),
        y: rows.map((r) => r['Null Percentage']),
        text: rows.map((r) => r['Column Name']),
        marker: {
          size: rows.map((r) => Math.max(8, r['Duplicate Count'])),
          sizemode: 'area',
          sizeref: 2 * Math.max(...rows.map((r) => r['Duplicate Count'] || 1), 1) / 40 ** 2,
          color: rows.map((r) => r['Risk Score']),
          colorscale: [[0, '#10b981'], [0.5, '#6366f1'], [1, '#ef4444']],
          showscale: true,
          colorbar: { title: 'Risk' },
        },
      }],
      layout: { xaxis: { title: 'Unique %' }, yaxis: { title: 'Null %' } },
    };
  }, [data]);

  // ─── Chart 8: Risk Score heatmap ────────────────────────────────────
  const chart8 = useMemo(() => {
    if (!data) return null;
    const rows = data.risk_heatmap;
    return {
      data: [{
        type: 'heatmap',
        z: [rows.map((r) => r['Risk Score'])],
        x: rows.map((r) => r['Column Name']),
        y: ['Risk Score'],
        colorscale: [[0, '#10b981'], [0.5, '#6366f1'], [1, '#ef4444']],
      }],
      layout: { xaxis: { tickangle: -45 } },
    };
  }, [data]);

  // ─── Chart 9: Risk Level radar ──────────────────────────────────────
  const chart9 = useMemo(() => {
    if (!data) return null;
    const rows = data.risk_radar;
    return {
      data: [{
        type: 'scatterpolar', fill: 'toself',
        r: rows.map((r) => r.value),
        theta: rows.map((r) => r.label),
        line: { color: '#6366f1' },
        fillcolor: 'rgba(99,102,241,0.12)',
      }],
      layout: { polar: { bgcolor: '#ffffff' } },
    };
  }, [data]);

  // ─── Chart 10: Length radar ─────────────────────────────────────────
  const chart10 = useMemo(() => {
    if (!data) return null;
    const rows = data.length_radar;
    return {
      data: [{
        type: 'scatterpolar', fill: 'toself',
        r: rows.map((r) => r.value),
        theta: rows.map((r) => r.label),
        line: { color: '#10b981' },
        fillcolor: 'rgba(16,185,129,0.12)',
      }],
      layout: { polar: { bgcolor: '#ffffff' } },
    };
  }, [data]);

  // ─── Chart 11: Type donut ───────────────────────────────────────────
  const chart11 = useMemo(() => {
    if (!data) return null;
    const rows = data.type_donut;
    return {
      data: [{
        type: 'pie', hole: 0.5,
        labels: rows.map((r) => r.label),
        values: rows.map((r) => r.value),
        marker: { colors: ['#3b82f6', '#6366f1', '#93c5fd', '#f59e0b'] },
      }],
      layout: {},
    };
  }, [data]);

  // ─── Chart 12: Risk donut ───────────────────────────────────────────
  const chart12 = useMemo(() => {
    if (!data) return null;
    const rows = data.risk_donut;
    const colorMap = { Low: '#10b981', Medium: '#f59e0b', High: '#ef4444' };
    return {
      data: [{
        type: 'pie', hole: 0.5,
        labels: rows.map((r) => r.label),
        values: rows.map((r) => r.value),
        marker: { colors: rows.map((r) => colorMap[r.label] || '#94a3b8') },
      }],
      layout: {},
    };
  }, [data]);

  // ─── Chart 13: Quality gauge ────────────────────────────────────────
  const chart13 = useMemo(() => {
    if (!data) return null;
    return {
      data: [{
        type: 'indicator',
        mode: 'gauge+number+delta',
        value: data.quality_gauge,
        title: { text: 'Quality Score' },
        delta: { reference: 80, increasing: { color: '#10b981' } },
        gauge: {
          axis: { range: [0, 100] },
          bar: { color: '#3b82f6' },
          bgcolor: '#f1f5f9',
          borderwidth: 2, bordercolor: '#e2e8f0',
          steps: [
            { range: [0, 50], color: '#fecaca' },
            { range: [50, 75], color: '#fef3c7' },
            { range: [75, 100], color: '#d1fae5' },
          ],
          threshold: { line: { color: '#1e40af', width: 4 }, thickness: 0.75, value: 90 },
        },
      }],
      layout: {},
    };
  }, [data]);

  // ─── Chart 14: Duplicate Risk gauge ─────────────────────────────────
  const chart14 = useMemo(() => {
    if (!data) return null;
    return {
      data: [{
        type: 'indicator',
        mode: 'gauge+number+delta',
        value: data.duplicate_risk_gauge,
        title: { text: 'Duplicate Risk' },
        delta: { reference: 20, decreasing: { color: '#10b981' } },
        gauge: {
          axis: { range: [0, 100] },
          bar: { color: '#f59e0b' },
          bgcolor: '#f1f5f9',
          borderwidth: 2, bordercolor: '#e2e8f0',
          steps: [
            { range: [0, 25], color: '#d1fae5' },
            { range: [25, 50], color: '#fef3c7' },
            { range: [50, 100], color: '#fecaca' },
          ],
          threshold: { line: { color: '#1e40af', width: 4 }, thickness: 0.75, value: 30 },
        },
      }],
      layout: {},
    };
  }, [data]);

  // ─── Chart 15: Unique vs Duplicate scatter ──────────────────────────
  const chart15 = useMemo(() => {
    if (!data) return null;
    const rows = data.scatter_unique_dup;
    const RISK_COLORS = { Low: '#10b981', Medium: '#f59e0b', High: '#ef4444' };
    const traces = ['Low', 'Medium', 'High'].map((lvl) => {
      const sub = rows.filter((r) => r['Risk Level'] === lvl);
      return {
        type: 'scatter', mode: 'markers', name: lvl,
        x: sub.map((r) => r['Unique Count']),
        y: sub.map((r) => r['Duplicate Count']),
        text: sub.map((r) => `${r['Column Name']} (Null: ${(r['Null Percentage'] || 0).toFixed(1)}%)`),
        marker: {
          size: sub.map((r) => Math.max(6, r['Risk Score'])),
          sizemode: 'area',
          color: RISK_COLORS[lvl],
        },
      };
    });
    return { data: traces, layout: { xaxis: { title: 'Unique Count' }, yaxis: { title: 'Duplicate Count' } } };
  }, [data]);

  // ─── Correlation matrix ─────────────────────────────────────────────
  const corrChart = useMemo(() => {
    if (!corr || !corr.columns?.length) return null;
    return {
      data: [{
        type: 'heatmap',
        z: corr.matrix, x: corr.columns, y: corr.columns,
        colorscale: 'RdBu', reversescale: true, zmin: -1, zmax: 1,
        text: corr.matrix.map((r) => r.map((v) => v.toFixed(2))),
        texttemplate: '%{text}',
        hovertemplate: '(%{x}, %{y}): %{z:.2f}<extra></extra>',
      }],
      layout: { xaxis: { tickangle: -45 } },
    };
  }, [corr]);

  if (loading) return <LinearProgress />;
  if (err) return <Alert severity="error">{err}</Alert>;
  if (!data) return null;

  return (
    <Box>
      <Typography sx={sectionHeaderSx}>Data Completeness Analysis</Typography>
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <Typography variant="subtitle2" mb={1}>Non-Null Count by Column</Typography>
          <PlotlyChart {...chart1} height={400} />
        </Grid>
        <Grid item xs={12} md={6}>
          <Typography variant="subtitle2" mb={1}>Non-Null vs Null Distribution</Typography>
          <PlotlyChart {...chart2} height={400} />
        </Grid>
      </Grid>

      <Typography sx={sectionHeaderSx}>Data Distribution Patterns</Typography>
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <Typography variant="subtitle2" mb={1}>Unique Count Distribution</Typography>
          <PlotlyChart {...chart3} height={400} />
        </Grid>
        <Grid item xs={12} md={6}>
          <Typography variant="subtitle2" mb={1}>Unique vs Duplicate Counts</Typography>
          <PlotlyChart {...chart4} height={400} />
        </Grid>
      </Grid>

      <Typography sx={sectionHeaderSx}>Trend &amp; Pattern Analysis</Typography>
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <Typography variant="subtitle2" mb={1}>Risk Score Trend</Typography>
          <PlotlyChart {...chart5} height={400} />
        </Grid>
        <Grid item xs={12} md={6}>
          <Typography variant="subtitle2" mb={1}>Null Percentage Distribution</Typography>
          <PlotlyChart {...chart6} height={400} />
        </Grid>
      </Grid>

      <Typography sx={sectionHeaderSx}>Advanced Analytics</Typography>
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <Typography variant="subtitle2" mb={1}>Unique % vs Null % (Bubble = Duplicate Count)</Typography>
          <PlotlyChart {...chart7} height={400} />
        </Grid>
        <Grid item xs={12} md={6}>
          <Typography variant="subtitle2" mb={1}>Risk Score Heatmap</Typography>
          <PlotlyChart {...chart8} height={400} />
        </Grid>
      </Grid>

      <Typography sx={sectionHeaderSx}>Radar Pattern Analysis</Typography>
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <Typography variant="subtitle2" mb={1}>Risk Level Distribution</Typography>
          <PlotlyChart {...chart9} height={400} />
        </Grid>
        <Grid item xs={12} md={6}>
          <Typography variant="subtitle2" mb={1}>Length Statistics</Typography>
          <PlotlyChart {...chart10} height={400} />
        </Grid>
      </Grid>

      <Typography sx={sectionHeaderSx}>Distribution Analysis</Typography>
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <Typography variant="subtitle2" mb={1}>Data Type Distribution</Typography>
          <PlotlyChart {...chart11} height={400} />
        </Grid>
        <Grid item xs={12} md={6}>
          <Typography variant="subtitle2" mb={1}>Risk Level Distribution</Typography>
          <PlotlyChart {...chart12} height={400} />
        </Grid>
      </Grid>

      <Typography sx={sectionHeaderSx}>Performance Gauges</Typography>
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <Typography variant="subtitle2" mb={1}>Overall Data Quality Score</Typography>
          <PlotlyChart {...chart13} height={400} />
        </Grid>
        <Grid item xs={12} md={6}>
          <Typography variant="subtitle2" mb={1}>Duplicate Risk Score</Typography>
          <PlotlyChart {...chart14} height={400} />
        </Grid>
      </Grid>

      <Typography sx={sectionHeaderSx}>Scatter Analytics</Typography>
      <Typography variant="subtitle2" mb={1}>Unique Count vs Duplicate Count (Bubble = Risk Score)</Typography>
      <PlotlyChart {...chart15} height={500} />

      {corr && corr.columns?.length >= 2 && (
        <>
          <Typography sx={sectionHeaderSx}>Correlation Matrix</Typography>
          <RadioGroup row value={corrMethod} onChange={(e) => setCorrMethod(e.target.value)} sx={{ mb: 1 }}>
            <FormControlLabel value="pearson" control={<Radio size="small" />} label="pearson" />
            <FormControlLabel value="spearman" control={<Radio size="small" />} label="spearman" />
          </RadioGroup>
          <PlotlyChart {...corrChart} height={Math.max(400, corr.columns.length * 28)} />
          {corr.high_pairs.length > 0 && (
            <>
              <Typography variant="subtitle2" mt={2} mb={1}>
                Highly correlated pairs (|r| ≥ 0.8):
              </Typography>
              <TableContainer component={Paper} sx={{ mb: 2 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Column A</TableCell>
                      <TableCell>Column B</TableCell>
                      <TableCell>Correlation</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {corr.high_pairs.map((p, i) => (
                      <TableRow key={i}>
                        <TableCell>{p['Column A']}</TableCell>
                        <TableCell>{p['Column B']}</TableCell>
                        <TableCell>{p['Correlation']}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </>
          )}
        </>
      )}

      <Typography sx={sectionHeaderSx}>Detailed Profiling Table</Typography>
      <TableContainer component={Paper} sx={{ maxHeight: 500 }}>
        <Table stickyHeader size="small">
          <TableHead>
            <TableRow>
              {Object.keys(detail[0] || {}).map((c) => (
                <TableCell key={c} sx={{ fontWeight: 600 }}>{c}</TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {detail.map((row, i) => (
              <TableRow key={i}>
                {Object.entries(row).map(([k, v]) => (
                  <TableCell key={k} sx={k === 'Risk Level' ? {
                    bgcolor: RISK_BG[v] || 'transparent',
                    color: RISK_FG[v] || 'inherit',
                    fontWeight: 600,
                  } : {}}>
                    {typeof v === 'number' ? (
                      Number.isInteger(v) ? v : v.toFixed(2)
                    ) : String(v)}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}
