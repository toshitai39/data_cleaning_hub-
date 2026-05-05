import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Box, Grid, Paper, Typography, Button, Stack, Alert, LinearProgress,
  Accordion, AccordionSummary, AccordionDetails, Divider, Table, TableBody,
  TableCell, TableContainer, TableHead, TableRow, Chip,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import UndoIcon from '@mui/icons-material/Undo';
import DownloadIcon from '@mui/icons-material/Download';
import api from '../api.js';
import PageHeader from '../components/PageHeader.jsx';
import EmptyState from '../components/EmptyState.jsx';
import { useDataset } from '../context/DatasetContext.jsx';
import ColumnRow from './quality/ColumnRow.jsx';
import AiRegexDialog from './quality/AiRegexDialog.jsx';
import {
  LibrarySaveDialog, LibraryLoadDialog, LibraryDeleteDialog,
} from './quality/LibraryDialogs.jsx';

function HeaderCell({ children, sm }) {
  return (
    <Grid item xs={12} sm={sm} sx={{ fontWeight: 700, color: 'text.secondary',
                                     fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: 0.6 }}>
      {children}
    </Grid>
  );
}

export default function DataQuality() {
  const { state, refresh } = useDataset();
  const [columns, setColumns] = useState([]);
  const [stats, setStats] = useState({ rows: 0, columns: 0, rejected: 0, total_rules: 0, history_count: 0 });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const [aiOpen, setAiOpen] = useState(false);
  const [saveOpen, setSaveOpen] = useState(false);
  const [loadOpen, setLoadOpen] = useState(false);
  const [delOpen, setDelOpen] = useState(false);
  const [history, setHistory] = useState([]);
  const [rejected, setRejected] = useState({ total: 0, preview: [] });
  const importInput = useRef(null);

  const loadAll = async () => {
    if (!state.loaded) return;
    try {
      const [colsR, cfgR, hisR, rejR] = await Promise.all([
        api.get('/quality/columns'),
        api.get('/quality/config'),
        api.get('/quality/history'),
        api.get('/quality/rejected'),
      ]);
      setColumns(colsR.data);
      setStats({
        rows: cfgR.data.rows, columns: cfgR.data.columns,
        rejected: cfgR.data.rejected, total_rules: cfgR.data.total_rules,
        history_count: cfgR.data.history_count,
      });
      setHistory(hisR.data);
      setRejected(rejR.data);
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Failed to load Data Quality state');
    }
  };

  useEffect(() => { loadAll(); }, [state.loaded]);

  const updateRowConfig = (col, newCfg) => {
    setColumns((prev) => prev.map((r) => r.column === col ? { ...r, config: newCfg } : r));
  };

  const applyAll = async () => {
    setBusy(true); setErr(''); setMsg('');
    try {
      const { data } = await api.post('/quality/apply-all');
      setMsg(`Applied ${data.applied} rule(s) across ${(data.columns || []).length} column(s); rejected ${data.rejected ?? 0}`);
      await loadAll(); await refresh();
    } catch (e) { setErr(e?.response?.data?.detail || 'Failed'); }
    finally { setBusy(false); }
  };

  const undo = async () => {
    setBusy(true); setErr(''); setMsg('');
    try {
      await api.post('/quality/undo');
      setMsg('Undone');
      await loadAll(); await refresh();
    } catch (e) { setErr(e?.response?.data?.detail || 'Failed'); }
    finally { setBusy(false); }
  };

  const enableAll = async () => { await api.post('/quality/enable-all'); loadAll(); };
  const disableAll = async () => { await api.post('/quality/disable-all'); loadAll(); };
  const clearRules = async () => { await api.post('/quality/clear-rules'); loadAll(); };

  const downloadRejected = async () => {
    try {
      const res = await api.post('/quality/download-rejected', null, { responseType: 'blob' });
      const cd = res.headers['content-disposition'] || '';
      const m = cd.match(/filename="?([^"]+)"?/);
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([res.data]));
      a.download = m ? m[1] : 'rejected.xlsx'; a.click();
    } catch (e) { setErr('Download failed'); }
  };

  const exportRules = async () => {
    try {
      const res = await api.get('/quality/export-rules', { responseType: 'blob' });
      const cd = res.headers['content-disposition'] || '';
      const m = cd.match(/filename="?([^"]+)"?/);
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([res.data]));
      a.download = m ? m[1] : 'dq_rules.json'; a.click();
    } catch (e) { setErr('Export failed'); }
  };

  const importRules = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    try {
      const { data } = await api.post('/quality/import-rules', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setMsg(`Imported rules for ${data.imported} columns`);
      loadAll();
    } catch (err) {
      setErr('Import failed');
    }
    e.target.value = '';
  };

  const columnNames = useMemo(() => columns.map((c) => c.column), [columns]);

  if (!state.loaded) {
    return (
      <>
        <PageHeader title="Data Quality" subtitle="Per-column rule editor with 6 modes." />
        <EmptyState />
      </>
    );
  }

  return (
    <>
      <PageHeader title="Data Quality" />
      {busy && <LinearProgress sx={{ mb: 2 }} />}
      {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}
      {msg && <Alert severity="success" sx={{ mb: 2 }}>{msg}</Alert>}

      {/* Top bar: Rows / Columns / Rejected / AI Regex / Apply / Undo */}
      <Grid container spacing={1.5} sx={{ mb: 2 }}>
        <Grid item xs={4} md={2}>
          <Paper sx={{ p: 1.5, textAlign: 'center' }}>
            <Typography variant="caption" color="text.secondary">Rows</Typography>
            <Typography variant="h6">{stats.rows.toLocaleString()}</Typography>
          </Paper>
        </Grid>
        <Grid item xs={4} md={2}>
          <Paper sx={{ p: 1.5, textAlign: 'center' }}>
            <Typography variant="caption" color="text.secondary">Columns</Typography>
            <Typography variant="h6">{stats.columns}</Typography>
          </Paper>
        </Grid>
        <Grid item xs={4} md={2}>
          <Paper sx={{ p: 1.5, textAlign: 'center' }}>
            <Typography variant="caption" color="text.secondary">Rejected</Typography>
            <Typography variant="h6">{stats.rejected.toLocaleString()}</Typography>
          </Paper>
        </Grid>
        <Grid item xs={4} md={2}>
          <Button fullWidth size="large" variant="outlined" startIcon={<AutoAwesomeIcon />}
            onClick={() => setAiOpen(true)}>AI Regex</Button>
        </Grid>
        <Grid item xs={4} md={2}>
          <Button fullWidth size="large" variant="contained"
            disabled={stats.total_rules === 0} onClick={applyAll}>
            Apply ({stats.total_rules})
          </Button>
        </Grid>
        <Grid item xs={4} md={2}>
          <Button fullWidth size="large" variant="outlined" startIcon={<UndoIcon />}
            disabled={stats.history_count === 0} onClick={undo}>Undo</Button>
        </Grid>
      </Grid>

      {/* Action buttons row */}
      <Grid container spacing={1.5} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}>
          <Button fullWidth variant="outlined" onClick={enableAll}>Enable All</Button>
        </Grid>
        <Grid item xs={6} md={3}>
          <Button fullWidth variant="outlined" onClick={disableAll}>Disable All</Button>
        </Grid>
        <Grid item xs={6} md={3}>
          <Button fullWidth variant="outlined" color="error" onClick={clearRules}>Clear Rules</Button>
        </Grid>
        <Grid item xs={6} md={3}>
          <Button fullWidth variant="outlined" startIcon={<DownloadIcon />}
            disabled={stats.rejected === 0} onClick={downloadRejected}>Download Rejected</Button>
        </Grid>
      </Grid>

      {/* Library row */}
      <Grid container spacing={1.5} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}>
          <Button fullWidth variant="outlined" onClick={() => setSaveOpen(true)}>Save to Library</Button>
        </Grid>
        <Grid item xs={6} md={3}>
          <Button fullWidth variant="outlined" onClick={() => setLoadOpen(true)}>Load from Library</Button>
        </Grid>
        <Grid item xs={6} md={3}>
          <Button fullWidth variant="outlined" color="error" onClick={() => setDelOpen(true)}>
            Delete from Library
          </Button>
        </Grid>
        <Grid item xs={6} md={3} />
      </Grid>

      {/* Import / Export rules JSON */}
      <Grid container spacing={1.5} sx={{ mb: 2 }}>
        <Grid item xs={12} md={3}>
          <Button fullWidth variant="outlined" startIcon={<DownloadIcon />}
            disabled={stats.total_rules === 0 && stats.columns === 0} onClick={exportRules}>
            Export Rules (JSON)
          </Button>
        </Grid>
        <Grid item xs={12} md={3}>
          <Button fullWidth variant="outlined" component="label">
            Import Rules
            <input type="file" hidden accept=".json" ref={importInput} onChange={importRules} />
          </Button>
        </Grid>
      </Grid>

      <Divider sx={{ mb: 1 }} />

      {/* Column rows */}
      <Paper variant="outlined" sx={{ p: 1.5 }}>
        <Grid container alignItems="center" spacing={1}
              sx={{ pb: 1, borderBottom: '1px solid', borderColor: 'divider' }}>
          <HeaderCell sm={1}>On</HeaderCell>
          <HeaderCell sm={2}>Column</HeaderCell>
          <HeaderCell sm={2}>Values</HeaderCell>
          <HeaderCell sm={2}>Rules</HeaderCell>
          <HeaderCell sm={1}>Mode</HeaderCell>
          <HeaderCell sm={2}>Configuration</HeaderCell>
          <HeaderCell sm={1}>Preview</HeaderCell>
          <HeaderCell sm={0.5}>Save</HeaderCell>
          <HeaderCell sm={0.5}>Run</HeaderCell>
        </Grid>
        {columns.map((row) => (
          <ColumnRow key={row.column} row={row}
            onConfigChange={updateRowConfig} onRefresh={loadAll} />
        ))}
      </Paper>

      {/* History */}
      {history.length > 0 && (
        <Accordion sx={{ mt: 2 }}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography>History ({history.length})</Typography>
          </AccordionSummary>
          <AccordionDetails>
            {history.slice().reverse().map((h, i) => (
              <Typography key={i} variant="caption" sx={{ display: 'block' }} color="text.secondary">
                {history.length - i}. {h.description} — {h.timestamp}
                {h.rejected_count > 0 && ` (${h.rejected_count} rejected)`}
              </Typography>
            ))}
          </AccordionDetails>
        </Accordion>
      )}

      {/* Rejected */}
      {rejected.total > 0 && (
        <Accordion sx={{ mt: 2 }}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography>Rejected ({rejected.total})</Typography>
          </AccordionSummary>
          <AccordionDetails>
            <TableContainer component={Paper} variant="outlined">
              <Table size="small">
                <TableHead>
                  <TableRow>
                    {Object.keys(rejected.preview[0] || {}).map((c) => (
                      <TableCell key={c} sx={{ fontWeight: 600 }}>{c}</TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {rejected.preview.map((r, i) => (
                    <TableRow key={i}>
                      {Object.entries(r).map(([k, v]) => (
                        <TableCell key={k}>{String(v ?? '')}</TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            <Chip label="Showing first 50 rows" size="small" sx={{ mt: 1 }} />
          </AccordionDetails>
        </Accordion>
      )}

      <AiRegexDialog open={aiOpen} onClose={() => setAiOpen(false)} columns={columnNames} />
      <LibrarySaveDialog open={saveOpen} onClose={() => setSaveOpen(false)}
        onDone={(name) => setMsg(`Saved rule set '${name}'`)} />
      <LibraryLoadDialog open={loadOpen} onClose={() => setLoadOpen(false)}
        onDone={(name, n) => { setMsg(`Loaded '${name}' (${n} columns)`); loadAll(); }} />
      <LibraryDeleteDialog open={delOpen} onClose={() => setDelOpen(false)}
        onDone={(name) => setMsg(`Deleted '${name}'`)} />
    </>
  );
}
