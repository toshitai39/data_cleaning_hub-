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

function ChartCard({ title, subtitle, children }) {
  return (
    <Paper
      elevation={0}
      sx={{
        p: 2.5,
        borderRadius: 2,
        border: '1px solid',
        borderColor: 'divider',
        bgcolor: '#ffffff',
      }}
    >
      <Box sx={{ mb: 1.5 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, color: 'text.primary', lineHeight: 1.3 }}>
          {title}
        </Typography>
        {subtitle && (
          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
            {subtitle}
          </Typography>
        )}
      </Box>
      {children}
    </Paper>
  );
}

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
        hovertemplate: '<b>%{y}</b><br>Non-Null: %{x:,}<extra></extra>',
      }],
      layout: {
        showlegend: false,
        xaxis: { type: 'linear', title: { text: 'Non-Null Count' } },
        yaxis: { type: 'category' },
      },
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
          marker: { color: '#6366f1' },
          hovertemplate: '<b>%{y}</b><br>Non-Null: %{x:,}<extra></extra>' },
        { type: 'bar', orientation: 'h', name: 'Null',
          y: rows.map((r) => r['Column Name']), x: rows.map((r) => r['Null Count']),
          marker: { color: '#ef4444' },
          hovertemplate: '<b>%{y}</b><br>Null: %{x:,}<extra></extra>' },
      ],
      layout: {
        barmode: 'stack',
        xaxis: { type: 'linear', title: { text: 'Row Count' } },
        yaxis: { type: 'category' },
      },
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
        hovertemplate: '<b>%{x}</b><br>Unique: %{y:,}<extra></extra>',
      }],
      layout: {
        showlegend: false,
        xaxis: { type: 'category', tickangle: -45 },
        yaxis: { type: 'linear', title: { text: 'Unique Count' } },
      },
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
          marker: { color: '#10b981' },
          hovertemplate: '<b>%{x}</b><br>Unique: %{y:,}<extra></extra>' },
        { type: 'bar', name: 'Duplicate',
          x: rows.map((r) => r['Column Name']),
          y: rows.map((r) => r['Duplicate Count']),
          marker: { color: '#f59e0b' },
          hovertemplate: '<b>%{x}</b><br>Duplicate: %{y:,}<extra></extra>' },
      ],
      layout: {
        barmode: 'stack',
        xaxis: { type: 'category', tickangle: -45 },
        yaxis: { type: 'linear', title: { text: 'Row Count' } },
      },
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
        hovertemplate: '<b>%{x}</b><br>Risk: %{y}<extra></extra>',
      }],
      layout: {
        showlegend: false,
        xaxis: { type: 'category', tickangle: -45 },
        yaxis: { type: 'linear', title: { text: 'Risk Score' }, range: [0, 100] },
      },
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
        hovertemplate: '<b>%{x}</b><br>Null: %{y:.2f}%<extra></extra>',
      }],
      layout: {
        showlegend: false,
        xaxis: { type: 'category', tickangle: -45 },
        yaxis: { type: 'linear', title: { text: 'Null %' }, range: [0, 100] },
      },
    };
  }, [data]);

  // ─── Chart 7: Unique% vs Null% bubble ───────────────────────────────
  const chart7 = useMemo(() => {
    if (!data) return null;
    const rows = data.scatter_unique_null;
    const maxDup = Math.max(...rows.map((r) => r['Duplicate Count'] || 1), 1);
    return {
      data: [{
        type: 'scatter', mode: 'markers',
        x: rows.map((r) => r['Unique Percentage']),
        y: rows.map((r) => r['Null Percentage']),
        text: rows.map((r) => r['Column Name']),
        hovertemplate: '<b>%{text}</b><br>Unique: %{x:.1f}%<br>Null: %{y:.1f}%<extra></extra>',
        marker: {
          size: rows.map((r) => Math.max(10, r['Duplicate Count'] || 0)),
          sizemode: 'area',
          sizeref: (2 * maxDup) / 40 ** 2,
          sizemin: 6,
          color: rows.map((r) => r['Risk Score']),
          colorscale: [[0, '#10b981'], [0.5, '#6366f1'], [1, '#ef4444']],
          showscale: true,
          colorbar: { title: { text: 'Risk' }, thickness: 14, len: 0.7 },
          line: { color: '#ffffff', width: 1 },
        },
      }],
      layout: {
        showlegend: false,
        xaxis: { type: 'linear', title: { text: 'Unique %' }, range: [0, 100] },
        yaxis: { type: 'linear', title: { text: 'Null %' }, range: [0, 100] },
      },
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
        zmin: 0,
        zmax: 100,
        colorbar: { title: { text: 'Risk' }, thickness: 14, len: 0.7 },
        hovertemplate: '<b>%{x}</b><br>Risk: %{z}<extra></extra>',
        xgap: 2,
        ygap: 2,
      }],
      layout: {
        xaxis: { type: 'category', tickangle: -45 },
        yaxis: { type: 'category' },
      },
    };
  }, [data]);

  // ─── Chart 9: Risk Level radar ──────────────────────────────────────
  const chart9 = useMemo(() => {
    if (!data) return null;
    const rows = data.risk_radar;
    const values = rows.map((r) => r.value);
    const maxVal = Math.max(...values, 1);
    return {
      data: [{
        type: 'scatterpolar', fill: 'toself',
        r: values,
        theta: rows.map((r) => r.label),
        line: { color: '#6366f1', width: 2 },
        marker: { size: 8, color: '#6366f1' },
        fillcolor: 'rgba(99,102,241,0.18)',
        hovertemplate: '<b>%{theta}</b><br>Count: %{r}<extra></extra>',
      }],
      layout: {
        showlegend: false,
        polar: {
          bgcolor: '#fafbfc',
          radialaxis: { visible: true, range: [0, maxVal * 1.1], gridcolor: '#e2e8f0' },
          angularaxis: { gridcolor: '#e2e8f0' },
        },
        margin: { l: 40, r: 40, t: 40, b: 40 },
      },
    };
  }, [data]);

  // ─── Chart 10: Length radar ─────────────────────────────────────────
  const chart10 = useMemo(() => {
    if (!data) return null;
    const rows = data.length_radar;
    const values = rows.map((r) => r.value);
    const maxVal = Math.max(...values, 1);
    return {
      data: [{
        type: 'scatterpolar', fill: 'toself',
        r: values,
        theta: rows.map((r) => r.label),
        line: { color: '#10b981', width: 2 },
        marker: { size: 8, color: '#10b981' },
        fillcolor: 'rgba(16,185,129,0.18)',
        hovertemplate: '<b>%{theta}</b><br>Value: %{r}<extra></extra>',
      }],
      layout: {
        showlegend: false,
        polar: {
          bgcolor: '#fafbfc',
          radialaxis: { visible: true, range: [0, maxVal * 1.1], gridcolor: '#e2e8f0' },
          angularaxis: { gridcolor: '#e2e8f0' },
        },
        margin: { l: 60, r: 60, t: 40, b: 40 },
      },
    };
  }, [data]);

  // ─── Chart 11: Type donut ───────────────────────────────────────────
  const chart11 = useMemo(() => {
    if (!data) return null;
    const rows = data.type_donut;
    return {
      data: [{
        type: 'pie', hole: 0.55,
        labels: rows.map((r) => r.label),
        values: rows.map((r) => r.value),
        marker: { colors: ['#3b82f6', '#6366f1', '#93c5fd', '#f59e0b'], line: { color: '#ffffff', width: 2 } },
        textinfo: 'label+percent',
        textposition: 'outside',
        hovertemplate: '<b>%{label}</b><br>Count: %{value}<br>%{percent}<extra></extra>',
      }],
      layout: { showlegend: false, margin: { l: 40, r: 40, t: 40, b: 40 } },
    };
  }, [data]);

  // ─── Chart 12: Risk donut ───────────────────────────────────────────
  const chart12 = useMemo(() => {
    if (!data) return null;
    const rows = data.risk_donut;
    const colorMap = { Low: '#10b981', Medium: '#f59e0b', High: '#ef4444' };
    return {
      data: [{
        type: 'pie', hole: 0.55,
        labels: rows.map((r) => r.label),
        values: rows.map((r) => r.value),
        marker: {
          colors: rows.map((r) => colorMap[r.label] || '#94a3b8'),
          line: { color: '#ffffff', width: 2 },
        },
        textinfo: 'label+percent',
        textposition: 'outside',
        hovertemplate: '<b>%{label}</b><br>Count: %{value}<br>%{percent}<extra></extra>',
      }],
      layout: { showlegend: false, margin: { l: 40, r: 40, t: 40, b: 40 } },
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
        hovertemplate: '<b>%{text}</b><br>Unique: %{x:,}<br>Duplicate: %{y:,}<extra></extra>',
        marker: {
          size: sub.map((r) => Math.max(10, r['Risk Score'] || 6)),
          sizemode: 'area',
          sizemin: 6,
          color: RISK_COLORS[lvl],
          line: { color: '#ffffff', width: 1 },
          opacity: 0.85,
        },
      };
    });
    return {
      data: traces,
      layout: {
        xaxis: { type: 'linear', title: { text: 'Unique Count' } },
        yaxis: { type: 'linear', title: { text: 'Duplicate Count' } },
      },
    };
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
        textfont: { size: 11 },
        hovertemplate: '<b>%{x}</b> × <b>%{y}</b>: %{z:.2f}<extra></extra>',
        colorbar: { thickness: 14, len: 0.7 },
        xgap: 1, ygap: 1,
      }],
      layout: {
        xaxis: { type: 'category', tickangle: -45 },
        yaxis: { type: 'category' },
      },
    };
  }, [corr]);

  if (loading) return <LinearProgress />;
  if (err) return <Alert severity="error">{err}</Alert>;
  if (!data) return null;

  return (
    <Box>
      <Typography sx={sectionHeaderSx}>Data Completeness Analysis</Typography>
      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <ChartCard title="Non-Null Count by Column" subtitle="Sorted by populated values">
            <PlotlyChart {...chart1} height={420} />
          </ChartCard>
        </Grid>
        <Grid item xs={12} md={6}>
          <ChartCard title="Non-Null vs Null Distribution" subtitle="Stacked composition per column">
            <PlotlyChart {...chart2} height={420} />
          </ChartCard>
        </Grid>
      </Grid>

      <Typography sx={sectionHeaderSx}>Data Distribution Patterns</Typography>
      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <ChartCard title="Unique Count Distribution" subtitle="Top columns by distinct values">
            <PlotlyChart {...chart3} height={420} />
          </ChartCard>
        </Grid>
        <Grid item xs={12} md={6}>
          <ChartCard title="Unique vs Duplicate Counts" subtitle="Composition of each column">
            <PlotlyChart {...chart4} height={420} />
          </ChartCard>
        </Grid>
      </Grid>

      <Typography sx={sectionHeaderSx}>Trend &amp; Pattern Analysis</Typography>
      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <ChartCard title="Risk Score Trend" subtitle="Per-column risk rating">
            <PlotlyChart {...chart5} height={420} />
          </ChartCard>
        </Grid>
        <Grid item xs={12} md={6}>
          <ChartCard title="Null Percentage Distribution" subtitle="Where missing values concentrate">
            <PlotlyChart {...chart6} height={420} />
          </ChartCard>
        </Grid>
      </Grid>

      <Typography sx={sectionHeaderSx}>Advanced Analytics</Typography>
      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <ChartCard title="Unique % vs Null %" subtitle="Bubble size = duplicate count, color = risk">
            <PlotlyChart {...chart7} height={420} />
          </ChartCard>
        </Grid>
        <Grid item xs={12} md={6}>
          <ChartCard title="Risk Score Heatmap" subtitle="Per-column risk intensity">
            <PlotlyChart {...chart8} height={420} />
          </ChartCard>
        </Grid>
      </Grid>

      <Typography sx={sectionHeaderSx}>Radar Pattern Analysis</Typography>
      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <ChartCard title="Risk Level Distribution" subtitle="Low / medium / high counts">
            <PlotlyChart {...chart9} height={420} />
          </ChartCard>
        </Grid>
        <Grid item xs={12} md={6}>
          <ChartCard title="Length Statistics" subtitle="Min / mean / max value lengths">
            <PlotlyChart {...chart10} height={420} />
          </ChartCard>
        </Grid>
      </Grid>

      <Typography sx={sectionHeaderSx}>Distribution Analysis</Typography>
      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <ChartCard title="Data Type Distribution" subtitle="Share of inferred dtypes">
            <PlotlyChart {...chart11} height={420} />
          </ChartCard>
        </Grid>
        <Grid item xs={12} md={6}>
          <ChartCard title="Risk Level Breakdown" subtitle="Columns by risk bucket">
            <PlotlyChart {...chart12} height={420} />
          </ChartCard>
        </Grid>
      </Grid>

      <Typography sx={sectionHeaderSx}>Performance Gauges</Typography>
      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <ChartCard title="Overall Data Quality Score" subtitle="Target: 80+">
            <PlotlyChart {...chart13} height={420} />
          </ChartCard>
        </Grid>
        <Grid item xs={12} md={6}>
          <ChartCard title="Duplicate Risk Score" subtitle="Target: under 20">
            <PlotlyChart {...chart14} height={420} />
          </ChartCard>
        </Grid>
      </Grid>

      <Typography sx={sectionHeaderSx}>Scatter Analytics</Typography>
      <ChartCard
        title="Unique Count vs Duplicate Count"
        subtitle="Bubble size scales with risk score"
        height={520}
      >
        <PlotlyChart {...chart15} height={520} />
      </ChartCard>

      {corr && corr.columns?.length >= 2 && (
        <>
          <Typography sx={sectionHeaderSx}>Correlation Matrix</Typography>
          <ChartCard
            title={`Pairwise correlation (${corrMethod})`}
            subtitle="Reds = positive, blues = negative"
            height={Math.max(420, corr.columns.length * 28)}
          >
            <RadioGroup
              row
              value={corrMethod}
              onChange={(e) => setCorrMethod(e.target.value)}
              sx={{ mb: 1 }}
            >
              <FormControlLabel value="pearson" control={<Radio size="small" />} label="Pearson" />
              <FormControlLabel value="spearman" control={<Radio size="small" />} label="Spearman" />
            </RadioGroup>
            <PlotlyChart {...corrChart} height={Math.max(400, corr.columns.length * 28)} />
          </ChartCard>
          {corr.high_pairs.length > 0 && (
            <Paper
              elevation={0}
              sx={{
                mt: 2,
                p: 2.5,
                borderRadius: 2,
                border: '1px solid',
                borderColor: 'divider',
              }}
            >
              <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1.5 }}>
                Highly correlated pairs (|r| ≥ 0.8)
              </Typography>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ fontWeight: 600 }}>Column A</TableCell>
                      <TableCell sx={{ fontWeight: 600 }}>Column B</TableCell>
                      <TableCell sx={{ fontWeight: 600 }} align="right">Correlation</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {corr.high_pairs.map((p, i) => (
                      <TableRow key={i}>
                        <TableCell>{p['Column A']}</TableCell>
                        <TableCell>{p['Column B']}</TableCell>
                        <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                          {p['Correlation']}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Paper>
          )}
        </>
      )}

      <Typography sx={sectionHeaderSx}>Detailed Profiling Table</Typography>
      <Paper
        elevation={0}
        sx={{
          borderRadius: 2,
          border: '1px solid',
          borderColor: 'divider',
          overflow: 'hidden',
        }}
      >
        <TableContainer sx={{ maxHeight: 520 }}>
          <Table stickyHeader size="small">
            <TableHead>
              <TableRow>
                {Object.keys(detail[0] || {}).map((c) => (
                  <TableCell
                    key={c}
                    sx={{
                      fontWeight: 600,
                      bgcolor: '#f8fafc',
                      color: 'text.secondary',
                      fontSize: '0.72rem',
                      letterSpacing: '0.04em',
                      textTransform: 'uppercase',
                    }}
                  >
                    {c}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {detail.map((row, i) => (
                <TableRow key={i} hover>
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
      </Paper>
    </Box>
  );
}
