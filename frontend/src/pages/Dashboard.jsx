import { useEffect, useState } from 'react';
import {
  Box, Grid, Paper, Typography, Alert, LinearProgress, Stack, Divider,
} from '@mui/material';
import api from '../api.js';
import EmptyState from '../components/EmptyState.jsx';
import PageHeader from '../components/PageHeader.jsx';
import { useDataset } from '../context/DatasetContext.jsx';
import PlotlyChart from './profiling/PlotlyChart.jsx';

// 1:1 colour palette from features/dashboard/ui.py
const DTYPE_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#64748b'];
const SEVERITY_COLORS = {
  critical: '#dc2626', warning: '#d97706', info: '#3b82f6',
};

function Kpi({ label, value }) {
  return (
    <Box sx={{
      bgcolor: '#FBFAFC',
      border: '1px solid #E7E6E6',
      borderRadius: 1.5,
      px: 2.25,
      py: 2,
      minHeight: 86,
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
    }}>
      <Typography sx={{
        fontFamily: "'Open Sans', sans-serif",
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: '0.1em',
        color: '#8A8A8A',
        textTransform: 'uppercase',
        mb: 0.75,
      }}>{label}</Typography>
      <Typography sx={{
        fontFamily: "'Montserrat', sans-serif",
        fontSize: 26,
        fontWeight: 700,
        color: '#1A1A1A',
        lineHeight: 1,
      }}>{value}</Typography>
    </Box>
  );
}

function QualityGauge({ score }) {
  if (typeof score !== 'number') {
    return <Alert severity="info">Run profiling to see the quality gauge.</Alert>;
  }
  return (
    <PlotlyChart
      data={[{
        type: 'indicator',
        mode: 'gauge+number',
        value: score,
        title: { text: 'Quality Score' },
        gauge: {
          axis: { range: [0, 100] },
          bar: { color: '#3b82f6' },
          steps: [
            { range: [0, 40], color: '#fecaca' },
            { range: [40, 70], color: '#fef3c7' },
            { range: [70, 100], color: '#d1fae5' },
          ],
        },
      }]}
      layout={{
        paper_bgcolor: '#ffffff',
        font: { color: '#334155' },
        margin: { t: 40, b: 10, l: 10, r: 10 },
      }}
      height={280}
    />
  );
}

function TopIssues({ issues }) {
  if (!issues || issues.length === 0) {
    return <Alert severity="success">No issues detected — your data looks clean.</Alert>;
  }
  return (
    <Stack spacing={0.75}>
      {issues.map((it, i) => (
        <Box key={i} sx={{
          borderLeft: `4px solid ${SEVERITY_COLORS[it.severity] || '#64748b'}`,
          px: 1.5, py: 0.75, my: 0.25,
          bgcolor: '#f8fafc',
          borderRadius: '0 6px 6px 0',
          fontSize: '0.85rem',
        }}>
          {it.message}
        </Box>
      ))}
    </Stack>
  );
}

function DTypeDonut({ distribution }) {
  const labels = Object.keys(distribution || {});
  const values = labels.map((k) => distribution[k]);
  if (labels.length === 0) return <Alert severity="info">No type info available.</Alert>;
  return (
    <PlotlyChart
      data={[{
        type: 'pie',
        labels, values,
        hole: 0.45,
        marker: { colors: DTYPE_COLORS },
      }]}
      layout={{
        paper_bgcolor: '#ffffff',
        font: { color: '#334155' },
        margin: { t: 20, b: 20, l: 10, r: 10 },
      }}
      height={320}
    />
  );
}

function NullBar({ topNull }) {
  if (!topNull || topNull.length === 0) {
    return <Alert severity="success">No missing values in any critical data element.</Alert>;
  }
  // Streamlit uses autorange: reversed on the y-axis so the highest is on top.
  return (
    <PlotlyChart
      data={[{
        type: 'bar',
        orientation: 'h',
        x: topNull.map((c) => c.null_pct),
        y: topNull.map((c) => c.column),
        marker: { color: '#ef4444' },
      }]}
      layout={{
        plot_bgcolor: '#ffffff',
        paper_bgcolor: '#ffffff',
        font: { color: '#334155' },
        margin: { l: 120, r: 10, t: 10, b: 30 },
        yaxis: { autorange: 'reversed' },
      }}
      height={320}
    />
  );
}

export default function Dashboard() {
  const { state } = useDataset();
  const [data, setData] = useState(null);
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!state.loaded) return;
    setLoading(true); setErr('');
    api.get('/profile/dashboard')
      .then((r) => setData(r.data))
      .catch((e) => setErr(e?.response?.data?.detail || 'Failed to load dashboard'))
      .finally(() => setLoading(false));
  }, [state.loaded, state.rows, state.operations]);

  if (!state.loaded) {
    return (
      <>
        <PageHeader title="Dashboard" subtitle="Executive summary" />
        <EmptyState message="Load a dataset to see the dashboard." />
      </>
    );
  }

  return (
    <>
      <PageHeader title="Dashboard" subtitle={`Snapshot of ${state.filename || 'your dataset'}`} />
      {loading && <LinearProgress sx={{ mb: 2 }} />}
      {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}

      {data && (
        <>
          {/* KPI row — 6 cards, mirrors _kpi() */}
          <Grid container spacing={1.5}>
            <Grid item xs={6} sm={4} md={2}>
              <Kpi label="Rows" value={(data.rows ?? 0).toLocaleString()} />
            </Grid>
            <Grid item xs={6} sm={4} md={2}>
              <Kpi label="Critical data elements" value={data.columns ?? 0} />
            </Grid>
            <Grid item xs={6} sm={4} md={2}>
              <Kpi label="Missing Cells" value={(data.missing_cells ?? 0).toLocaleString()} />
            </Grid>
            <Grid item xs={6} sm={4} md={2}>
              <Kpi label="Missing %" value={`${data.missing_percentage ?? 0}%`} />
            </Grid>
            <Grid item xs={6} sm={4} md={2}>
              <Kpi label="Duplicates" value={(data.duplicate_rows ?? 0).toLocaleString()} />
            </Grid>
            <Grid item xs={6} sm={4} md={2}>
              <Kpi label="Quality Score"
                value={typeof data.quality_score === 'number'
                  ? data.quality_score.toFixed(0)
                  : '--'} />
            </Grid>
          </Grid>

          <Divider sx={{ my: 3 }} />

          {/* Quality gauge + Top Issues — 1:2 split like Streamlit */}
          <Grid container spacing={2}>
            <Grid item xs={12} md={4}>
              <Paper sx={{ p: 2 }}>
                <QualityGauge score={data.quality_score} />
              </Paper>
            </Grid>
            <Grid item xs={12} md={8}>
              <Paper sx={{ p: 2 }}>
                <Typography variant="h6" gutterBottom>Top Issues</Typography>
                <TopIssues issues={data.top_issues} />
              </Paper>
            </Grid>
          </Grid>

          <Divider sx={{ my: 3 }} />

          {/* Data type donut + Null bar — 1:1 split */}
          <Grid container spacing={2}>
            <Grid item xs={12} md={6}>
              <Paper sx={{ p: 2 }}>
                <Typography variant="h6" gutterBottom>Data Type Distribution</Typography>
                <DTypeDonut distribution={data.dtype_distribution} />
              </Paper>
            </Grid>
            <Grid item xs={12} md={6}>
              <Paper sx={{ p: 2 }}>
                <Typography variant="h6" gutterBottom>Top Missing-Value Critical Data Elements</Typography>
                <NullBar topNull={data.top_null_columns} />
              </Paper>
            </Grid>
          </Grid>

          {/* Risk overview — only when profiles available */}
          {data.has_profiles && (
            <>
              <Typography variant="h6" sx={{ mt: 3, mb: 1.5 }}>Critical Data Element Risk Overview</Typography>
              <Grid container spacing={2}>
                <Grid item xs={4}>
                  <Paper sx={{ p: 2.5, textAlign: 'center' }}>
                    <Typography variant="caption" color="text.secondary"
                      sx={{ textTransform: 'uppercase', letterSpacing: 0.6 }}>Low Risk</Typography>
                    <Typography variant="h4" sx={{ color: '#10b981', fontWeight: 700 }}>
                      {data.risk_counts?.Low ?? 0}
                    </Typography>
                  </Paper>
                </Grid>
                <Grid item xs={4}>
                  <Paper sx={{ p: 2.5, textAlign: 'center' }}>
                    <Typography variant="caption" color="text.secondary"
                      sx={{ textTransform: 'uppercase', letterSpacing: 0.6 }}>Medium Risk</Typography>
                    <Typography variant="h4" sx={{ color: '#f59e0b', fontWeight: 700 }}>
                      {data.risk_counts?.Medium ?? 0}
                    </Typography>
                  </Paper>
                </Grid>
                <Grid item xs={4}>
                  <Paper sx={{ p: 2.5, textAlign: 'center' }}>
                    <Typography variant="caption" color="text.secondary"
                      sx={{ textTransform: 'uppercase', letterSpacing: 0.6 }}>High Risk</Typography>
                    <Typography variant="h4" sx={{ color: '#ef4444', fontWeight: 700 }}>
                      {data.risk_counts?.High ?? 0}
                    </Typography>
                  </Paper>
                </Grid>
              </Grid>
            </>
          )}

          {/* Recent operations */}
          {data.recent_operations && data.recent_operations.length > 0 && (
            <>
              <Divider sx={{ my: 3 }} />
              <Typography variant="h6" gutterBottom>Recent Operations</Typography>
              <Stack spacing={0.5}>
                {data.recent_operations.map((op, i) => (
                  <Typography key={i} variant="caption" color="text.secondary">
                    {op.timestamp || ''} — {op.operation || op.type || JSON.stringify(op)}
                    {op.rows ? ` (${op.rows.toLocaleString()} rows)` : ''}
                    {op.removed ? ` (${op.removed} removed)` : ''}
                  </Typography>
                ))}
              </Stack>
            </>
          )}
        </>
      )}
    </>
  );
}
