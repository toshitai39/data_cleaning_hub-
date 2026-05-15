import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Box, Stack, Typography, Button, Alert, LinearProgress, Paper, Chip,
  Tabs, Tab, Menu, MenuItem, IconButton, Divider,
  Accordion, AccordionSummary, AccordionDetails,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import UndoIcon from '@mui/icons-material/Undo';
import DownloadIcon from '@mui/icons-material/Download';
import UploadIcon from '@mui/icons-material/Upload';
import HistoryIcon from '@mui/icons-material/History';
import RuleFolderOutlinedIcon from '@mui/icons-material/RuleFolderOutlined';
import DoNotDisturbAltIcon from '@mui/icons-material/DoNotDisturbAlt';
import DeleteSweepOutlinedIcon from '@mui/icons-material/DeleteSweepOutlined';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import api from '../api.js';
import PageHeader from '../components/PageHeader.jsx';
import EmptyState from '../components/EmptyState.jsx';
import { useDataset } from '../context/DatasetContext.jsx';
import DimensionTab from './quality/DimensionTab.jsx';
import CrossFieldPanel from './quality/CrossFieldPanel.jsx';
import {
  LibrarySaveDialog, LibraryLoadDialog, LibraryDeleteDialog,
} from './quality/LibraryDialogs.jsx';

// Mirrors the Rule Generator palette — same dimension → same color
// so the steward's eye doesn't have to relearn the legend.
const DIMENSION_PALETTE = {
  Completeness:              { fg: '#14532d', tint: '#f0fdf4', dot: '#16a34a' },
  Validation:                { fg: '#581c87', tint: '#faf5ff', dot: '#9333ea' },
  Standardisation:           { fg: '#713f12', tint: '#fefce8', dot: '#ca8a04' },
  Uniqueness:                { fg: '#0c4a6e', tint: '#f0f9ff', dot: '#0284c7' },
  Accuracy:                  { fg: '#1e3a8a', tint: '#eef2ff', dot: '#3b82f6' },
  Timeliness:                { fg: '#134e4a', tint: '#f0fdfa', dot: '#0d9488' },
  'Cross-field Validation':  { fg: '#7c2d12', tint: '#fff7ed', dot: '#ea580c' },
};
const DIM_FALLBACK = { fg: '#475569', tint: '#f1f5f9', dot: '#64748b' };
const dimStyle = (d) => DIMENSION_PALETTE[d] || DIM_FALLBACK;

function ProgressTile({ label, value, denominator, tone = 'neutral' }) {
  // Muted palette — the number is the focal point; color is just a hint.
  const palette = {
    neutral: { fg: '#1A1A1A', sub: '#8A8A8A' },
    good:    { fg: '#15803d', sub: '#64748b' },
    bad:     { fg: '#b91c1c', sub: '#8A8A8A' },
  }[tone];
  return (
    <Box sx={{
      bgcolor: '#FBFAFC',
      border: '1px solid #E7E6E6',
      borderRadius: 1.5,
      px: 2,
      py: 1.5,
      minWidth: 140,
      flex: 1,
    }}>
      <Typography sx={{
        fontSize: 10.5, fontWeight: 700, letterSpacing: '0.1em',
        color: '#8A8A8A', textTransform: 'uppercase', mb: 0.5,
      }}>{label}</Typography>
      <Typography sx={{
        fontFamily: "'Montserrat', sans-serif",
        fontSize: 22, fontWeight: 700, color: palette.fg, lineHeight: 1,
      }}>
        {value}
        {denominator !== undefined && (
          <Typography component="span" sx={{
            fontSize: 13, fontWeight: 500, color: palette.sub, ml: 0.5,
          }}>/ {denominator}</Typography>
        )}
      </Typography>
    </Box>
  );
}

export default function DataQuality() {
  const { state, refresh } = useDataset();
  const [byDim, setByDim] = useState(null);
  const [activeDim, setActiveDim] = useState('Completeness');
  const autoPickedRef = useRef(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const [menuEl, setMenuEl] = useState(null);
  const [saveOpen, setSaveOpen] = useState(false);
  const [loadOpen, setLoadOpen] = useState(false);
  const [delOpen, setDelOpen] = useState(false);
  const [history, setHistory] = useState([]);
  const [rejected, setRejected] = useState({ total: 0, preview: [] });
  const importInput = useRef(null);

  const loadAll = async () => {
    if (!state.loaded) return;
    try {
      const [dimR, hisR, rejR] = await Promise.all([
        api.get('/quality/by-dimension'),
        api.get('/quality/history'),
        api.get('/quality/rejected'),
      ]);
      setByDim(dimR.data);
      setHistory(hisR.data);
      setRejected(rejR.data);
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Failed to load Cleansing state');
    }
  };

  useEffect(() => { loadAll(); }, [state.loaded]);

  // On first load, jump to whichever dimension has work to do so the
  // steward doesn't land on an empty Completeness tab. After that we
  // respect the user's tab choice — the ref-guard prevents re-jumping
  // every time loadAll() refreshes byDim.
  useEffect(() => {
    if (!byDim || autoPickedRef.current) return;
    const hasWork = (d) => (d.pending_count + d.unimported_count + (d.manual_count || 0)) > 0;
    const found = (byDim.dimensions || []).find(hasWork);
    if (found && found.name !== activeDim) {
      setActiveDim(found.name);
    }
    autoPickedRef.current = true;
  }, [byDim, activeDim]);

  const dropEmptyColumns = async () => {
    const empties = (byDim?.empty_columns || []).map((c) => c.column);
    if (empties.length === 0) return;
    if (!window.confirm(`Drop ${empties.length} empty CDE${empties.length === 1 ? '' : 's'} from the working dataset? Original file is untouched.`)) return;
    setBusy(true); setErr(''); setMsg('');
    try {
      const { data } = await api.post('/quality/drop-columns', { columns: empties });
      setMsg(`Dropped ${data.dropped.length} empty CDE${data.dropped.length === 1 ? '' : 's'}`);
      await loadAll();
      await refresh();
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Drop failed');
    } finally { setBusy(false); }
  };

  const dropAllUnmapped = async () => {
    if (!window.confirm(`Drop ${totals.unmapped} unmapped rules? They can't be converted to an executable check.`)) return;
    setBusy(true); setErr(''); setMsg('');
    try {
      const { data } = await api.post('/quality/drop-unmapped');
      setMsg(`Dropped ${data.dropped} unmapped rule${data.dropped === 1 ? '' : 's'}`);
      await loadAll();
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Drop failed');
    } finally { setBusy(false); }
  };

  const resetAll = async () => {
    if (!window.confirm('Reset all cleansing changes? Restores the working dataset to its original state. Rule definitions stay.')) return;
    setBusy(true); setErr(''); setMsg('');
    try {
      await api.post('/quality/reset-cleansing');
      setMsg('Working dataset restored to original');
      await loadAll();
      await refresh();
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Reset failed');
    } finally { setBusy(false); }
  };

  const undo = async () => {
    setBusy(true); setErr(''); setMsg('');
    try {
      await api.post('/quality/undo');
      setMsg('Undone');
      await loadAll();
      await refresh();
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Undo failed');
    } finally { setBusy(false); }
  };

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
      setMsg(`Imported rules for ${data.imported} CDEs`);
      loadAll();
    } catch (err) {
      setErr('Import failed');
    }
    e.target.value = '';
  };

  const totals = byDim?.totals || {
    generated: 0, actionable: 0, passed: 0, applied: 0, unmapped: 0,
    blocked_empty: 0, blocked_incomplete: 0, multi_cde: 0, invalid: 0,
    rejected: 0, history: 0, empty_columns: 0, failing_rows_total: 0,
  };
  // Cleanable denominator = rules we CAN act on now (actionable + applied).
  // Passing rules are good but not "progress". Blocked/unmapped/invalid
  // are out of scope until resolved separately.
  const cleanableRules = totals.actionable + totals.applied;
  const progressPct = cleanableRules > 0
    ? Math.round((totals.applied / cleanableRules) * 100)
    : 0;

  const dimensions = byDim?.dimensions || [];
  const activeDimData = useMemo(
    () => dimensions.find((d) => d.name === activeDim),
    [dimensions, activeDim],
  );

  if (!state.loaded) {
    return (
      <>
        <PageHeader title="Cleansing" subtitle="Dimension-driven cleansing with preview before every fix." />
        <EmptyState />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Cleansing"
        subtitle="Dimension-driven · preview-first · human-in-the-loop"
      />
      {busy && <LinearProgress sx={{ mb: 2 }} />}
      {err && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErr('')}>{err}</Alert>}
      {msg && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setMsg('')}>{msg}</Alert>}

      {/* ── Progress meter + global actions ───────────────────────────── */}
      <Paper variant="outlined" sx={{ p: 2.25, mb: 2.5 }}>
        <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 1.5 }}>
          <Box sx={{ flex: 1 }}>
            <Typography sx={{
              fontFamily: "'Montserrat', sans-serif",
              fontSize: 17, fontWeight: 700, color: '#1A1A1A',
            }}>
              Cleansing progress
            </Typography>
            <Typography sx={{ fontSize: 12, color: '#555555' }}>
              {totals.applied} of {cleanableRules} actionable rules applied · {progressPct}% complete
              {' · '}{(totals.generated || 0).toLocaleString()} total rules generated
            </Typography>
          </Box>
          <Button
            size="small"
            variant="outlined"
            startIcon={<UndoIcon />}
            onClick={undo}
            disabled={busy || totals.history === 0}
            sx={{ textTransform: 'none', fontWeight: 600 }}
          >
            Undo last
          </Button>
          <Button
            size="small"
            variant="outlined"
            color="warning"
            startIcon={<RestartAltIcon />}
            onClick={resetAll}
            disabled={busy || (totals.applied === 0 && totals.rejected === 0 && totals.history === 0)}
            sx={{ textTransform: 'none', fontWeight: 600 }}
          >
            Reset all
          </Button>
          <IconButton
            onClick={(e) => setMenuEl(e.currentTarget)}
            size="small"
            sx={{ border: '1px solid #E7E6E6' }}
          >
            <MoreVertIcon fontSize="small" />
          </IconButton>
          <Menu
            anchorEl={menuEl}
            open={!!menuEl}
            onClose={() => setMenuEl(null)}
            slotProps={{ paper: { sx: { minWidth: 220 } } }}
          >
            <MenuItem onClick={() => { setMenuEl(null); setSaveOpen(true); }}>
              <RuleFolderOutlinedIcon fontSize="small" sx={{ mr: 1 }} /> Save to rule library
            </MenuItem>
            <MenuItem onClick={() => { setMenuEl(null); setLoadOpen(true); }}>
              <RuleFolderOutlinedIcon fontSize="small" sx={{ mr: 1 }} /> Load from rule library
            </MenuItem>
            <MenuItem onClick={() => { setMenuEl(null); setDelOpen(true); }}>
              <RuleFolderOutlinedIcon fontSize="small" sx={{ mr: 1 }} /> Delete rule set
            </MenuItem>
            <Divider />
            <MenuItem onClick={() => { setMenuEl(null); exportRules(); }}>
              <DownloadIcon fontSize="small" sx={{ mr: 1 }} /> Export rules (JSON)
            </MenuItem>
            <MenuItem component="label">
              <UploadIcon fontSize="small" sx={{ mr: 1 }} /> Import rules (JSON)
              <input type="file" hidden accept=".json" ref={importInput} onChange={(e) => { setMenuEl(null); importRules(e); }} />
            </MenuItem>
          </Menu>
        </Stack>

        <LinearProgress
          variant="determinate"
          value={progressPct}
          sx={{
            height: 10,
            borderRadius: 5,
            bgcolor: '#F4ECF9',
            '& .MuiLinearProgress-bar': { bgcolor: '#6A28A8', borderRadius: 5 },
            mb: 2,
          }}
        />

        <Stack direction="row" spacing={1.5} flexWrap="wrap">
          <ProgressTile label="Actionable" value={totals.actionable} tone={totals.actionable > 0 ? 'bad' : 'good'} />
          <ProgressTile label="Passed" value={totals.passed} tone="good" />
          <ProgressTile label="Applied" value={totals.applied} tone="good" />
          <ProgressTile label="Unmapped" value={totals.unmapped} />
          <ProgressTile label="Blocked" value={(totals.blocked_empty || 0) + (totals.blocked_incomplete || 0)} />
          <ProgressTile label="Invalid" value={totals.invalid} />
          <ProgressTile label="Rejected rows" value={totals.rejected.toLocaleString()} tone={totals.rejected > 0 ? 'bad' : 'neutral'} />
        </Stack>
        {totals.failing_rows_total > 0 && (
          <Typography sx={{ mt: 1.5, fontSize: 12, color: '#b91c1c', fontWeight: 600 }}>
            {totals.failing_rows_total.toLocaleString()} failing rows across all dimensions — open Actionable filter on each tab to clean.
          </Typography>
        )}
      </Paper>

      {/* ── Empty CDE banner ──────────────────────────────────────────── */}
      {(byDim?.empty_columns || []).length > 0 && (
        <Alert
          severity="warning"
          icon={<DoNotDisturbAltIcon />}
          sx={{ mb: 2 }}
          action={
            <Button
              color="inherit"
              size="small"
              startIcon={<DeleteSweepOutlinedIcon />}
              onClick={dropEmptyColumns}
              disabled={busy}
              sx={{ textTransform: 'none', fontWeight: 700 }}
            >
              Drop {byDim.empty_columns.length} empty CDE{byDim.empty_columns.length === 1 ? '' : 's'}
            </Button>
          }
        >
          <b>{byDim.empty_columns.length}</b> CDE{byDim.empty_columns.length === 1 ? ' is' : 's are'} 100% empty
          — applying rules to {byDim.empty_columns.length === 1 ? 'it' : 'them'} produces no signal.
          {' '}
          <Typography component="span" sx={{ fontSize: 12, color: '#92400e' }}>
            ({(byDim.empty_columns || []).slice(0, 5).map((c) => c.column).join(', ')}
            {byDim.empty_columns.length > 5 && `, +${byDim.empty_columns.length - 5} more`})
          </Typography>
        </Alert>
      )}

      {/* ── Unmapped rules banner ─────────────────────────────────────── */}
      {totals.unmapped > 0 && (
        <Alert
          severity="info"
          icon={<DoNotDisturbAltIcon />}
          sx={{ mb: 2 }}
          action={
            <Button
              color="inherit"
              size="small"
              startIcon={<DeleteSweepOutlinedIcon />}
              onClick={dropAllUnmapped}
              disabled={busy}
              sx={{ textTransform: 'none', fontWeight: 700 }}
            >
              Drop {totals.unmapped} unmapped
            </Button>
          }
        >
          <b>{totals.unmapped}</b> AI rule{totals.unmapped === 1 ? '' : 's'} couldn't be converted
          to a mechanical check (e.g. casing intent, judgement calls). They produce no signal —
          dismiss them here, or review one by one under the <b>Unmapped</b> filter on each dimension tab.
        </Alert>
      )}

      {/* ── Dimension tabs ────────────────────────────────────────────── */}
      <Paper variant="outlined" sx={{ p: 2.25 }}>
        <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
          <Tabs
            value={activeDim}
            onChange={(_, v) => setActiveDim(v)}
            variant="scrollable"
            scrollButtons="auto"
            TabIndicatorProps={{
              sx: { height: 3, borderRadius: 2, bgcolor: dimStyle(activeDim).dot },
            }}
            sx={{ minHeight: 40, '& .MuiTab-root': { minHeight: 40, py: 1, textTransform: 'none' } }}
          >
            {dimensions.map((d) => {
              const style = dimStyle(d.name);
              const active = activeDim === d.name;
              // Show the RG-generated total so an "all clean" dimension
              // still reads as "25" — the steward sees it was checked.
              const totalForDim = d.generated_count
                ?? (d.pending_count + d.applied_count + d.unimported_count + (d.manual_count || 0));
              return (
                <Tab
                  key={d.name}
                  value={d.name}
                  label={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                      <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: style.dot }} />
                      <Typography
                        variant="body2"
                        sx={{ fontWeight: active ? 700 : 500, color: active ? style.fg : 'text.primary' }}
                      >
                        {d.name}
                      </Typography>
                      <Chip
                        size="small"
                        label={totalForDim}
                        sx={{
                          height: 18, fontSize: '0.7rem', fontWeight: 600,
                          bgcolor: active ? style.tint : 'rgba(0,0,0,0.06)',
                          color: active ? style.fg : 'text.secondary',
                        }}
                      />
                    </Box>
                  }
                />
              );
            })}
          </Tabs>
        </Box>

        {activeDim === 'Cross-field Validation' ? (
          <CrossFieldPanel onAfterFix={loadAll} />
        ) : (
          <DimensionTab
            dimension={activeDim}
            data={activeDimData}
            onAfterChange={async () => { await loadAll(); await refresh(); }}
          />
        )}
      </Paper>

      {/* ── Rejected (most important review step) ─────────────────────── */}
      {rejected.total > 0 && (
        <Accordion sx={{ mt: 2.5 }} defaultExpanded>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Stack direction="row" alignItems="center" spacing={1.25}>
              <Typography sx={{ fontWeight: 700 }}>
                Rejected rows
              </Typography>
              <Chip
                size="small"
                label={rejected.total.toLocaleString()}
                sx={{ height: 20, fontSize: '0.7rem', bgcolor: '#fef2f2', color: '#b91c1c', fontWeight: 700 }}
              />
              <Typography sx={{ fontSize: 12, color: '#8A8A8A' }}>
                · review before exporting cleaned data
              </Typography>
            </Stack>
          </AccordionSummary>
          <AccordionDetails>
            <Stack direction="row" justifyContent="flex-end" sx={{ mb: 1 }}>
              <Button
                size="small"
                variant="outlined"
                startIcon={<DownloadIcon />}
                onClick={downloadRejected}
                sx={{ textTransform: 'none', fontWeight: 600 }}
              >
                Download rejected (.xlsx)
              </Button>
            </Stack>
            <TableContainer component={Paper} variant="outlined">
              <Table size="small">
                <TableHead>
                  <TableRow>
                    {Object.keys(rejected.preview[0] || {}).map((c) => (
                      <TableCell key={c} sx={{ fontWeight: 700 }}>{c}</TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {rejected.preview.map((r, i) => (
                    <TableRow key={i}>
                      {Object.entries(r).map(([k, v]) => (
                        <TableCell key={k} sx={{ fontFamily: 'ui-monospace, Menlo, monospace', fontSize: '0.75rem' }}>
                          {String(v ?? '')}
                        </TableCell>
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

      {/* ── History ───────────────────────────────────────────────────── */}
      {history.length > 0 && (
        <Accordion sx={{ mt: 1.5 }}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Stack direction="row" alignItems="center" spacing={1.25}>
              <HistoryIcon fontSize="small" sx={{ color: '#8A8A8A' }} />
              <Typography sx={{ fontWeight: 700 }}>
                History
              </Typography>
              <Chip size="small" label={history.length} sx={{ height: 20, fontSize: '0.7rem' }} />
            </Stack>
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

      <LibrarySaveDialog open={saveOpen} onClose={() => setSaveOpen(false)}
        onDone={(name) => setMsg(`Saved rule set '${name}'`)} />
      <LibraryLoadDialog open={loadOpen} onClose={() => setLoadOpen(false)}
        onDone={(name, n) => { setMsg(`Loaded '${name}' (${n} CDEs)`); loadAll(); }} />
      <LibraryDeleteDialog open={delOpen} onClose={() => setDelOpen(false)}
        onDone={(name) => setMsg(`Deleted '${name}'`)} />
    </>
  );
}
