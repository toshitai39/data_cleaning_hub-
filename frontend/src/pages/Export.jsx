import { useEffect, useMemo, useState } from 'react';
import {
  Box, Grid, Paper, Stack, Typography, Button, Alert, LinearProgress, Divider,
  TextField, MenuItem, FormControl, InputLabel, Select, OutlinedInput, Slider,
  FormControlLabel, Checkbox, Accordion, AccordionSummary, AccordionDetails,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import DownloadIcon from '@mui/icons-material/Download';
import api from '../api.js';
import PageHeader from '../components/PageHeader.jsx';
import EmptyState from '../components/EmptyState.jsx';
import { useDataset } from '../context/DatasetContext.jsx';

const FORMATS = ['CSV', 'Excel', 'Parquet', 'JSON', 'Feather'];
const ENCODINGS = ['utf-8', 'latin-1', 'utf-16'];
const COMPRESSIONS = ['none', 'gzip', 'zip', 'bz2'];
const DELIMITERS = [
  { v: ',', label: ',' },
  { v: ';', label: ';' },
  { v: '\t', label: 'Tab (\\t)' },
  { v: '|', label: '|' },
];
const QUOTE_CHARS = ['"', "'"];

function safeStr(v) {
  if (v == null) return '';
  return String(v);
}

export default function Export() {
  const { state } = useDataset();
  const [format, setFormat] = useState('CSV');
  const [allColumns, setAllColumns] = useState([]);
  const [selectedCols, setSelectedCols] = useState([]);
  const [samplePct, setSamplePct] = useState(100);
  const [includeIndex, setIncludeIndex] = useState(false);
  const [encoding, setEncoding] = useState('utf-8');
  const [compression, setCompression] = useState('none');
  const [delimiter, setDelimiter] = useState(',');
  const [quotechar, setQuoteChar] = useState('"');
  const [previewRows, setPreviewRows] = useState([]);
  const [previewCount, setPreviewCount] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');

  // Batch export
  const [rowsPerFile, setRowsPerFile] = useState(100000);

  useEffect(() => {
    if (!state.loaded) return;
    api.get('/data/preview-full', { params: { page: 1, page_size: 10 } })
      .then((r) => {
        setAllColumns(r.data.columns);
        setSelectedCols(r.data.columns);
        setPreviewRows(r.data.rows);
        setPreviewCount(r.data.total_rows);
      })
      .catch((e) => setErr(e?.response?.data?.detail || 'Failed to load preview'));
  }, [state.loaded]);

  const exportRowCount = useMemo(() => {
    return Math.round((samplePct / 100) * previewCount);
  }, [samplePct, previewCount]);

  const downloadBlob = async (path, body, defaultName) => {
    setBusy(true); setErr(''); setMsg('');
    try {
      const res = await api.post(path, body, { responseType: 'blob' });
      const cd = res.headers['content-disposition'] || '';
      const m = cd.match(/filename="?([^"]+)"?/);
      const filename = m ? m[1] : defaultName;
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([res.data]));
      a.download = filename; a.click();
      URL.revokeObjectURL(a.href);
      setMsg(`Downloaded ${filename}`);
    } catch (e) {
      // blob errors hide the JSON detail; try to read it
      try {
        const text = await e?.response?.data?.text();
        const j = JSON.parse(text);
        setErr(j.detail || 'Export failed');
      } catch {
        setErr('Export failed');
      }
    } finally { setBusy(false); }
  };

  const generateExport = () => {
    const body = {
      format,
      columns: selectedCols.length === allColumns.length ? null : selectedCols,
      sample_pct: samplePct,
      include_index: includeIndex,
      encoding,
      compression,
      delimiter,
      quotechar,
    };
    downloadBlob('/export/single', body, `export.${format.toLowerCase()}`);
  };

  const generateBatch = () => {
    const body = {
      format,
      rows_per_file: rowsPerFile,
      columns: selectedCols.length > 0 ? selectedCols : null,
    };
    downloadBlob('/export/batch', body, 'batch_export.zip');
  };

  const downloadHtmlReport = () =>
    downloadBlob('/export/report/html', null, 'profiling_report.html');
  const downloadPdfReport = () =>
    downloadBlob('/export/report/pdf', null, 'profiling_report.pdf');

  const isLargeDataset = previewCount > 100000;
  const showBatch = previewCount > 500000;

  if (!state.loaded) {
    return (
      <>
        <PageHeader title="Export Data" />
        <EmptyState message="No data to export" />
      </>
    );
  }

  return (
    <>
      <PageHeader title="Export Data" />

      {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}
      {msg && <Alert severity="success" sx={{ mb: 2 }}>{msg}</Alert>}

      <Paper sx={{ p: 3, mb: 2 }}>
        <Typography variant="h6" sx={{ mb: 2 }}>Export Configuration</Typography>

        <Grid container spacing={2}>
          <Grid item xs={12} md={4}>
            <FormControl fullWidth size="small">
              <InputLabel>Format</InputLabel>
              <Select label="Format" value={format} onChange={(e) => setFormat(e.target.value)}>
                {FORMATS.map((f) => <MenuItem key={f} value={f}>{f}</MenuItem>)}
              </Select>
            </FormControl>
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
              {format === 'CSV' && 'Universal compatibility'}
              {format === 'Excel' && 'Best for analysis (limit 1M rows)'}
              {format === 'Parquet' && 'Compressed, fast, preserves types'}
              {format === 'JSON' && 'API-friendly'}
              {format === 'Feather' && 'Fast I/O for Python'}
            </Typography>
          </Grid>

          <Grid item xs={12} md={4}>
            <FormControl fullWidth size="small">
              <InputLabel>Critical data elements (empty = all)</InputLabel>
              <Select multiple value={selectedCols}
                onChange={(e) => setSelectedCols(typeof e.target.value === 'string'
                  ? e.target.value.split(',') : e.target.value)}
                input={<OutlinedInput label="Critical data elements (empty = all)" />}
                renderValue={(s) => s.length === allColumns.length ? 'All critical data elements' : s.join(', ')}>
                {allColumns.map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
              </Select>
            </FormControl>
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
              {selectedCols.length} of {allColumns.length} selected
            </Typography>
          </Grid>

          <Grid item xs={12} md={4}>
            {isLargeDataset ? (
              <>
                <Alert severity="warning" sx={{ mb: 1 }}>
                  Large dataset: {previewCount.toLocaleString()} rows
                </Alert>
                <Box>
                  <Typography variant="caption">Sample %: <b>{samplePct}</b></Typography>
                  <Slider value={samplePct} onChange={(_, v) => setSamplePct(v)}
                    min={1} max={100} step={1} />
                </Box>
              </>
            ) : (
              <Typography variant="caption" color="text.secondary">
                Dataset is small ({previewCount.toLocaleString()} rows) — full export.
              </Typography>
            )}
          </Grid>
        </Grid>

        <Accordion sx={{ mt: 2 }}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography>Advanced Options</Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Grid container spacing={2}>
              <Grid item xs={12} md={4}>
                <Stack spacing={1.5}>
                  <FormControlLabel
                    control={<Checkbox checked={includeIndex}
                      onChange={(e) => setIncludeIndex(e.target.checked)} />}
                    label="Include Index" />
                  <FormControl fullWidth size="small">
                    <InputLabel>Encoding</InputLabel>
                    <Select label="Encoding" value={encoding}
                      onChange={(e) => setEncoding(e.target.value)}>
                      {ENCODINGS.map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
                    </Select>
                  </FormControl>
                </Stack>
              </Grid>
              <Grid item xs={12} md={4}>
                <FormControl fullWidth size="small">
                  <InputLabel>Compression</InputLabel>
                  <Select label="Compression" value={compression}
                    onChange={(e) => setCompression(e.target.value)}>
                    {COMPRESSIONS.map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
                  </Select>
                </FormControl>
                <Typography variant="caption" color="text.secondary"
                  sx={{ mt: 0.5, display: 'block' }}>
                  For CSV/JSON only
                </Typography>
              </Grid>
              <Grid item xs={12} md={4}>
                {format === 'CSV' && (
                  <Stack spacing={1.5}>
                    <FormControl fullWidth size="small">
                      <InputLabel>Delimiter</InputLabel>
                      <Select label="Delimiter" value={delimiter}
                        onChange={(e) => setDelimiter(e.target.value)}>
                        {DELIMITERS.map((d) => (
                          <MenuItem key={d.v} value={d.v}>{d.label}</MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                    <FormControl fullWidth size="small">
                      <InputLabel>Quote char</InputLabel>
                      <Select label="Quote char" value={quotechar}
                        onChange={(e) => setQuoteChar(e.target.value)}>
                        {QUOTE_CHARS.map((q) => (
                          <MenuItem key={q} value={q}>{q}</MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  </Stack>
                )}
              </Grid>
            </Grid>
          </AccordionDetails>
        </Accordion>

        <Divider sx={{ my: 2 }} />

        <Typography variant="body2" sx={{ fontWeight: 700, mb: 1 }}>
          Export Preview: {exportRowCount.toLocaleString()} rows × {selectedCols.length} columns
        </Typography>

        <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 320, mb: 2 }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                {selectedCols.slice(0, 20).map((c) => (
                  <TableCell key={c} sx={{ fontWeight: 600 }}>{c}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {previewRows.slice(0, 10).map((r, i) => (
                <TableRow key={i}>
                  {selectedCols.slice(0, 20).map((c) => (
                    <TableCell key={c} sx={{ fontFamily: 'monospace', fontSize: '0.78rem' }}>
                      {safeStr(r[c]).slice(0, 200)}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>

        {busy && <LinearProgress sx={{ mb: 1 }} />}

        <Button fullWidth size="large" variant="contained" startIcon={<DownloadIcon />}
          onClick={generateExport} disabled={busy}>
          Generate Export File
        </Button>

        {showBatch && (
          <>
            <Divider sx={{ my: 3 }} />
            <Typography variant="h6" sx={{ mb: 1 }}>Batch Export (for very large files)</Typography>
            <Alert severity="info" sx={{ mb: 1.5 }}>Split large dataset into multiple files</Alert>
            <Grid container spacing={2} alignItems="center">
              <Grid item xs={12} sm={6}>
                <TextField fullWidth size="small" type="number" label="Rows per file"
                  value={rowsPerFile}
                  onChange={(e) => setRowsPerFile(Math.max(10000,
                    Math.min(1000000, parseInt(e.target.value || '100000', 10))))}
                  inputProps={{ min: 10000, max: 1000000, step: 10000 }} />
              </Grid>
              <Grid item xs={12} sm={6}>
                <Button fullWidth variant="outlined" startIcon={<DownloadIcon />}
                  onClick={generateBatch} disabled={busy}>
                  Generate Batch Export
                </Button>
              </Grid>
            </Grid>
          </>
        )}
      </Paper>

      {/* Profiling Report */}
      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" sx={{ mb: 0.5 }}>Profiling Report</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
          Download a formatted profiling report with executive summary, column profiles, and recommendations.
        </Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <Button fullWidth variant="outlined" startIcon={<DownloadIcon />}
              onClick={downloadHtmlReport} disabled={busy}>
              Generate HTML Report
            </Button>
          </Grid>
          <Grid item xs={12} md={6}>
            <Button fullWidth variant="outlined" startIcon={<DownloadIcon />}
              onClick={downloadPdfReport} disabled={busy}>
              Generate PDF Report
            </Button>
          </Grid>
        </Grid>
      </Paper>
    </>
  );
}
