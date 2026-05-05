import { useMemo, useState } from 'react';
import {
  Box, Paper, Typography, Button, Stack, Alert, LinearProgress, Chip,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
} from '@mui/material';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import api from '../api.js';
import PageHeader from '../components/PageHeader.jsx';
import PlotlyChart from './profiling/PlotlyChart.jsx';

export default function MultiFile() {
  const [files, setFiles] = useState([]);
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const onFiles = (e) => {
    const newOnes = Array.from(e.target.files || []);
    setFiles((prev) => {
      // dedupe by (name, size, lastModified) so the same file doesn't duplicate
      const existing = new Set(prev.map((f) => `${f.name}|${f.size}|${f.lastModified}`));
      const merged = [...prev];
      for (const f of newOnes) {
        const key = `${f.name}|${f.size}|${f.lastModified}`;
        if (!existing.has(key)) {
          merged.push(f);
          existing.add(key);
        }
      }
      return merged;
    });
    setData(null);
    setErr('');
    e.target.value = '';  // allow re-picking the same file later
  };

  const removeFile = (idx) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
    setData(null);
  };

  const clearAll = () => {
    setFiles([]);
    setData(null);
    setErr('');
  };

  const compare = async () => {
    if (files.length < 2) {
      setErr('Upload at least 2 files to compare.');
      return;
    }
    setBusy(true); setErr('');
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append('files', f));
      const { data: resp } = await api.post('/multi-file/compare', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setData(resp);
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Compare failed');
    } finally { setBusy(false); }
  };

  // Plotly grouped bar chart, one trace per file
  // (matches `px.bar(..., color="File", barmode="group")`)
  const nullChart = useMemo(() => {
    if (!data || data.null_chart_data.length === 0) return null;
    const fileColors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#a855f7', '#64748b'];
    // One trace per file
    const traces = data.files.map((fname, i) => {
      const rows = data.null_chart_data.filter((r) => r.File === fname);
      return {
        type: 'bar',
        name: fname,
        x: rows.map((r) => r.Column),
        y: rows.map((r) => r['Null %']),
        marker: { color: fileColors[i % fileColors.length] },
      };
    });
    return {
      data: traces,
      layout: {
        barmode: 'group',
        plot_bgcolor: '#ffffff',
        paper_bgcolor: '#ffffff',
        font: { color: '#334155' },
        xaxis: { title: 'Column', tickangle: -45 },
        yaxis: { title: 'Null %' },
        margin: { l: 50, r: 20, t: 20, b: 100 },
      },
    };
  }, [data]);

  return (
    <>
      <PageHeader title="Multi-File Profiling"
        subtitle="Upload multiple CSV / Excel files (e.g. monthly extracts) to compare their schemas and summary statistics side by side." />

      <Paper sx={{ p: 3, mb: 2 }}>
        <Stack spacing={2}>
          <Box sx={{
            border: '2px dashed', borderColor: 'divider', borderRadius: 2,
            p: 3, textAlign: 'center', bgcolor: '#f8fafc',
          }}>
            <CloudUploadIcon sx={{ fontSize: 36, color: 'primary.light', mb: 1 }} />
            <Typography variant="subtitle1" sx={{ mb: 0.5 }}>Upload files</Typography>
            <Typography variant="caption" color="text.secondary" sx={{ mb: 1.5, display: 'block' }}>
              Supported: .csv .tsv .xlsx .xls .parquet .json
            </Typography>
            <Stack direction="row" spacing={1} justifyContent="center">
              <Button variant="outlined" component="label">
                {files.length === 0 ? 'Pick files' : 'Add more files'}
                <input hidden multiple type="file"
                  accept=".csv,.tsv,.txt,.xlsx,.xls,.parquet,.json"
                  onChange={onFiles} />
              </Button>
              {files.length > 0 && (
                <Button variant="outlined" color="error" onClick={clearAll}>Clear</Button>
              )}
            </Stack>
            {files.length > 0 && (
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap mt={1.5} justifyContent="center">
                {files.map((f, i) => (
                  <Chip key={`${f.name}-${i}`} label={f.name} size="small"
                    onDelete={() => removeFile(i)} />
                ))}
              </Stack>
            )}
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
              {files.length} file{files.length === 1 ? '' : 's'} selected
            </Typography>
          </Box>

          <Button variant="contained" onClick={compare} disabled={busy || files.length < 2}>
            Compare
          </Button>

          {busy && <LinearProgress />}
          {err && <Alert severity="error">{err}</Alert>}
          {!data && !err && files.length < 2 && (
            <Alert severity="info">Upload at least 2 files to compare.</Alert>
          )}
        </Stack>
      </Paper>

      {data && (
        <>
          {/* Schema Comparison */}
          <Typography variant="h6" sx={{ mt: 2, mb: 1 }}>Schema Comparison</Typography>
          <TableContainer component={Paper} variant="outlined" sx={{ mb: 3, maxHeight: 480 }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 600 }}>Column</TableCell>
                  {data.files.map((f) => (
                    <TableCell key={f} sx={{ fontWeight: 600 }}>{f}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {data.schema_rows.map((row, i) => (
                  <TableRow key={i}>
                    <TableCell sx={{ fontWeight: 600 }}>{row.Column}</TableCell>
                    {data.files.map((f) => (
                      <TableCell key={f} sx={{
                        fontFamily: 'monospace', fontSize: '0.78rem',
                        bgcolor: row[f] === 'MISSING' ? '#fee2e2' : 'inherit',
                        color: row[f] === 'MISSING' ? '#991b1b' : 'inherit',
                        fontWeight: row[f] === 'MISSING' ? 700 : 'normal',
                      }}>
                        {row[f]}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          {/* File Statistics */}
          <Typography variant="h6" sx={{ mb: 1 }}>File Statistics</Typography>
          <TableContainer component={Paper} variant="outlined" sx={{ mb: 3 }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 600 }}>File</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Rows</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Columns</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Missing Cells</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Missing %</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.stats_rows.map((row, i) => (
                  <TableRow key={i}>
                    <TableCell>{row.File}</TableCell>
                    <TableCell>{row.Rows.toLocaleString()}</TableCell>
                    <TableCell>{row.Columns}</TableCell>
                    <TableCell>{row['Missing Cells'].toLocaleString()}</TableCell>
                    <TableCell>{row['Missing %']}%</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          {/* Null % chart for common columns */}
          {data.common_columns.length > 0 && nullChart && (
            <>
              <Typography variant="h6" sx={{ mb: 1 }}>Null % by Column (Common Columns)</Typography>
              <Paper variant="outlined" sx={{ p: 2 }}>
                <PlotlyChart data={nullChart.data} layout={nullChart.layout} height={400} />
              </Paper>
            </>
          )}

          {data.errors && data.errors.length > 0 && (
            <Alert severity="warning" sx={{ mt: 2 }}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>Some files could not be read:</Typography>
              {data.errors.map((e, i) => (
                <Typography key={i} variant="caption" sx={{ display: 'block' }}>
                  • {e.file}: {e.error}
                </Typography>
              ))}
            </Alert>
          )}
        </>
      )}
    </>
  );
}
