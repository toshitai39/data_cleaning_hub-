import { useEffect, useMemo, useState } from 'react';
import {
  Box, Grid, Paper, Stack, Typography, TextField, MenuItem, Button, Alert,
  LinearProgress, OutlinedInput, FormControl, InputLabel, Select, Divider,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Tooltip,
} from '@mui/material';
import DownloadIcon from '@mui/icons-material/Download';
import api from '../api.js';
import PageHeader from '../components/PageHeader.jsx';
import EmptyState from '../components/EmptyState.jsx';
import { useDataset } from '../context/DatasetContext.jsx';

const PAGE_SIZES = [100, 500, 1000, 5000, 10000];

function Metric({ label, value }) {
  return (
    <Paper sx={{ p: 2, textAlign: 'center' }}>
      <Typography variant="caption" color="text.secondary"
        sx={{ textTransform: 'uppercase', letterSpacing: 0.6 }}>{label}</Typography>
      <Typography variant="h6" sx={{ fontWeight: 700, color: 'primary.main' }}>{value}</Typography>
    </Paper>
  );
}

export default function Preview() {
  const { state } = useDataset();
  const [pageSize, setPageSize] = useState(100);
  const [page, setPage] = useState(1);
  const [pageInput, setPageInput] = useState(1);
  const [allColumns, setAllColumns] = useState([]);
  const [selectedCols, setSelectedCols] = useState([]);
  const [search, setSearch] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');

  // First load: fetch column list (and let backend default to all cols).
  useEffect(() => {
    if (!state.loaded) return;
    (async () => {
      try {
        const { data: d } = await api.get('/data/preview-full',
          { params: { page: 1, page_size: 1 } });
        setAllColumns(d.columns);
        // default to first 20 (matches Streamlit default)
        setSelectedCols(d.columns.slice(0, Math.min(20, d.columns.length)));
      } catch (e) {
        setErr(e?.response?.data?.detail || 'Failed');
      }
    })();
  }, [state.loaded]);

  const fetchPage = async () => {
    setLoading(true); setErr('');
    try {
      const params = { page, page_size: pageSize };
      if (selectedCols.length > 0 && selectedCols.length < allColumns.length) {
        params.columns = selectedCols.join(',');
      }
      if (search) params.search = search;
      const { data: d } = await api.get('/data/preview-full', { params });
      setData(d);
      setPageInput(d.page);
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Failed');
    } finally { setLoading(false); }
  };

  useEffect(() => {
    if (!state.loaded || allColumns.length === 0) return;
    fetchPage();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.loaded, page, pageSize, selectedCols.join(','), search, allColumns.length]);

  const totalPages = data?.total_pages || 1;
  const goto = (p) => {
    const clamped = Math.max(1, Math.min(totalPages, p));
    setPage(clamped);
    setPageInput(clamped);
  };

  const downloadCsv = async () => {
    try {
      const body = {
        page, page_size: pageSize,
        columns: selectedCols.length > 0 ? selectedCols : null,
        search: search || null,
      };
      const res = await api.post('/data/preview/download', body, { responseType: 'blob' });
      const cd = res.headers['content-disposition'] || '';
      const m = cd.match(/filename="?([^"]+)"?/);
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([res.data]));
      a.download = m ? m[1] : `preview_page_${page}.csv`;
      a.click();
    } catch (e) {
      setErr('Download failed');
    }
  };

  if (!state.loaded) {
    return (
      <>
        <PageHeader title="Preview" />
        <EmptyState message="No data loaded" />
      </>
    );
  }

  // Display rows + columns; respect what backend sent
  const cols = data?.selected_columns || selectedCols;
  const rows = data?.rows || [];
  const start = data?.start_idx ?? 0;
  const end = data?.end_idx ?? 0;

  return (
    <>
      <PageHeader title="Data Preview" />

      {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}

      {/* 4 metrics */}
      <Grid container spacing={1.5} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}>
          <Metric label="Total Rows" value={data ? data.total_rows.toLocaleString() : '—'} />
        </Grid>
        <Grid item xs={6} md={3}>
          <Metric label="Total Columns" value={data?.total_columns ?? '—'} />
        </Grid>
        <Grid item xs={6} md={3}>
          <Metric label="Memory" value={data ? `${data.memory_mb} MB` : '—'} />
        </Grid>
        <Grid item xs={6} md={3}>
          <Metric label="Data Types" value={data?.dtype_count ?? '—'} />
        </Grid>
      </Grid>

      <Divider sx={{ my: 2 }} />

      {/* Pagination row */}
      <Grid container spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
        <Grid item xs={6} md={2}>
          <FormControl fullWidth size="small">
            <InputLabel>Rows per page</InputLabel>
            <Select label="Rows per page" value={pageSize}
              onChange={(e) => { setPageSize(e.target.value); setPage(1); setPageInput(1); }}>
              {PAGE_SIZES.map((s) => <MenuItem key={s} value={s}>{s.toLocaleString()}</MenuItem>)}
            </Select>
          </FormControl>
        </Grid>
        <Grid item xs={6} md={2}>
          <TextField fullWidth size="small" type="number" label="Page" value={pageInput}
            onChange={(e) => setPageInput(parseInt(e.target.value || '1', 10))}
            onBlur={() => goto(pageInput)}
            onKeyDown={(e) => { if (e.key === 'Enter') goto(pageInput); }}
            inputProps={{ min: 1, max: totalPages }} />
        </Grid>
        <Grid item xs={6} md={2}>
          <Metric label="Total Pages" value={totalPages} />
        </Grid>
        <Grid item xs={12} md={6}>
          <Stack direction="row" spacing={1}>
            <Button fullWidth variant="outlined" onClick={() => goto(1)} disabled={page <= 1}>First</Button>
            <Button fullWidth variant="outlined" onClick={() => goto(page - 1)} disabled={page <= 1}>Prev</Button>
            <Button fullWidth variant="outlined" onClick={() => goto(page + 1)} disabled={page >= totalPages}>Next</Button>
            <Button fullWidth variant="outlined" onClick={() => goto(totalPages)} disabled={page >= totalPages}>Last</Button>
          </Stack>
        </Grid>
      </Grid>

      <Divider sx={{ my: 2 }} />

      {/* Column subset + search */}
      <Grid container spacing={1.5} sx={{ mb: 2 }}>
        <Grid item xs={12} md={9}>
          <FormControl fullWidth size="small">
            <InputLabel>Select columns to display</InputLabel>
            <Select multiple value={selectedCols}
              onChange={(e) => setSelectedCols(typeof e.target.value === 'string'
                ? e.target.value.split(',') : e.target.value)}
              input={<OutlinedInput label="Select columns to display" />}
              renderValue={(s) => s.join(', ')}>
              {allColumns.map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
            </Select>
          </FormControl>
        </Grid>
        <Grid item xs={12} md={3}>
          <TextField fullWidth size="small" label="Search in data"
            value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="case-insensitive" />
        </Grid>
      </Grid>

      {search && data && (
        <Alert severity="info" sx={{ mb: 1 }}>
          Search found {data.matched_count} matching {data.matched_count === 1 ? 'row' : 'rows'}
        </Alert>
      )}

      <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
        Showing rows {start.toLocaleString()} to {end.toLocaleString()} of {data ? data.total_rows.toLocaleString() : '—'}
      </Typography>

      {loading && <LinearProgress sx={{ mb: 1 }} />}

      <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 600, mb: 2 }}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              {cols.map((c) => (
                <Tooltip key={c} title={`Type: ${data?.dtypes?.[c] || ''}`}>
                  <TableCell sx={{ fontWeight: 600 }}>{c}</TableCell>
                </Tooltip>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((r, i) => (
              <TableRow key={i}>
                {cols.map((c) => (
                  <TableCell key={c} sx={{ fontFamily: 'monospace', fontSize: '0.78rem' }}>
                    {r[c] == null ? '' : String(r[c])}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      <Divider sx={{ my: 2 }} />

      <Button variant="outlined" startIcon={<DownloadIcon />} onClick={downloadCsv} fullWidth>
        Download Current View as CSV
      </Button>
    </>
  );
}
