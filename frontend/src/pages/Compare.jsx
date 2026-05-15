import { useEffect, useMemo, useState } from 'react';
import {
  Box, Grid, Paper, Typography, Stack, Button, Alert, LinearProgress, Chip,
  TextField, MenuItem, OutlinedInput, FormControl, InputLabel, Select,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  ToggleButton, ToggleButtonGroup, Tooltip, IconButton, Collapse,
} from '@mui/material';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import KeyboardArrowUpIcon from '@mui/icons-material/KeyboardArrowUp';
import TuneIcon from '@mui/icons-material/Tune';
import api from '../api.js';
import PageHeader from '../components/PageHeader.jsx';
import EmptyState from '../components/EmptyState.jsx';
import { useDataset } from '../context/DatasetContext.jsx';

// Calm, low-saturation palette — readable, client-grade.
const TONE = {
  modified: { bg: '#fef9c3', fg: '#854d0e' },   // amber
  added:    { bg: '#dcfce7', fg: '#166534' },   // emerald
  removed:  { bg: '#fee2e2', fg: '#991b1b' },   // rose
  neutral:  { bg: '#f1f5f9', fg: '#475569' },   // slate
};

const CHANGE_TYPE_TONE = {
  'Standardised':           { bg: '#e0e7ff', fg: '#3730a3' },
  'Standardised (mostly)':  { bg: '#e0e7ff', fg: '#3730a3' },
  'Cleared':                { bg: '#fef2f2', fg: '#b91c1c' },
  'Backfilled':             { bg: '#f0fdf4', fg: '#15803d' },
  'Modified':               { bg: '#fef9c3', fg: '#854d0e' },
};


function HeroKPI({ label, value, sub, accent }) {
  return (
    <Paper variant="outlined" sx={{
      p: 2, borderRadius: 2,
      bgcolor: accent ? '#FAFAFA' : '#FFFFFF',
      borderLeft: accent ? `3px solid ${accent}` : undefined,
    }}>
      <Typography sx={{
        fontSize: 10.5, fontWeight: 700, letterSpacing: '0.10em',
        color: '#8A8A8A', textTransform: 'uppercase', mb: 0.5,
      }}>
        {label}
      </Typography>
      <Typography sx={{
        fontFamily: "'Montserrat', sans-serif",
        fontSize: 26, fontWeight: 700, color: '#1A1A1A', lineHeight: 1.1,
        fontVariantNumeric: 'tabular-nums',
      }}>
        {value}
      </Typography>
      {sub && (
        <Typography sx={{ fontSize: 11.5, color: '#6B7280', mt: 0.5 }}>
          {sub}
        </Typography>
      )}
    </Paper>
  );
}


function buildNarrative(stats, byCol) {
  if (!stats) return '';
  const removed = stats.original_rows - stats.modified_rows;
  const cdeTouched = byCol?.cdes_touched || 0;
  const cellsChanged = byCol?.total_modified_cells || stats.modified_cells || 0;
  const topCol = (byCol?.columns || [])[0];

  if (removed === 0 && cellsChanged === 0) {
    return 'No changes have been applied yet — the working dataset is identical to the original.';
  }

  const parts = [];
  if (removed > 0) {
    parts.push(`removed ${removed.toLocaleString()} row${removed === 1 ? '' : 's'}`);
  }
  if (cellsChanged > 0) {
    parts.push(`modified ${cellsChanged.toLocaleString()} cell${cellsChanged === 1 ? '' : 's'} across ${cdeTouched} CDE${cdeTouched === 1 ? '' : 's'}`);
  }
  let s = `Cleansing ${parts.join(' and ')}.`;
  if (topCol) {
    s += ` The largest impact is on ${topCol.column} (${topCol.changed.toLocaleString()} ${topCol.change_type.toLowerCase()}).`;
  }
  return s;
}


function ChangeLedger({ byCol }) {
  const [expanded, setExpanded] = useState({});
  if (!byCol || !byCol.columns || byCol.columns.length === 0) {
    return null;
  }
  return (
    <Paper variant="outlined" sx={{ mb: 2.5 }}>
      <Box sx={{
        px: 2.5, py: 1.5, borderBottom: '1px solid #E5E7EB',
        display: 'flex', alignItems: 'baseline', gap: 1,
      }}>
        <Typography sx={{ fontSize: 15, fontWeight: 700, color: '#1A1A1A' }}>
          What changed, by Critical Data Element
        </Typography>
        <Typography sx={{ fontSize: 12, color: '#6B7280' }}>
          ({byCol.columns.length} CDE{byCol.columns.length === 1 ? '' : 's'} touched)
        </Typography>
      </Box>
      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow sx={{ '& th': { bgcolor: '#FAFAFA', fontWeight: 700,
              fontSize: '0.7rem', color: '#6B7280', textTransform: 'uppercase',
              letterSpacing: '0.08em' } }}>
              <TableCell sx={{ width: 36 }} />
              <TableCell>Critical Data Element</TableCell>
              <TableCell>Change type</TableCell>
              <TableCell align="right">Cells changed</TableCell>
              <TableCell>Breakdown</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {byCol.columns.map((c) => {
              const tone = CHANGE_TYPE_TONE[c.change_type] || TONE.neutral;
              const isOpen = !!expanded[c.column];
              return (
                <>
                  <TableRow key={c.column} hover sx={{
                    '& td': { borderBottom: isOpen ? 'none' : '1px solid #F1F1F1' },
                  }}>
                    <TableCell>
                      <IconButton size="small" onClick={() =>
                        setExpanded((p) => ({ ...p, [c.column]: !p[c.column] }))}>
                        {isOpen ? <KeyboardArrowUpIcon fontSize="small" /> : <KeyboardArrowDownIcon fontSize="small" />}
                      </IconButton>
                    </TableCell>
                    <TableCell sx={{ fontFamily: 'ui-monospace, Menlo, monospace',
                      fontSize: '0.82rem', fontWeight: 600 }}>
                      {c.column}
                    </TableCell>
                    <TableCell>
                      <Chip size="small" label={c.change_type}
                        sx={{ height: 22, fontSize: '0.7rem', fontWeight: 700,
                          bgcolor: tone.bg, color: tone.fg }} />
                    </TableCell>
                    <TableCell align="right" sx={{
                      fontVariantNumeric: 'tabular-nums', fontWeight: 600,
                    }}>
                      {c.changed.toLocaleString()}
                    </TableCell>
                    <TableCell sx={{ fontSize: '0.8rem', color: '#475569' }}>
                      {c.standardised > 0 && <span>std: {c.standardised}  ·  </span>}
                      {c.nulled > 0 && <span>cleared: {c.nulled}  ·  </span>}
                      {c.filled > 0 && <span>backfilled: {c.filled}  ·  </span>}
                      {(c.changed - c.standardised - c.nulled - c.filled) > 0 && (
                        <span>other: {c.changed - c.standardised - c.nulled - c.filled}</span>
                      )}
                    </TableCell>
                  </TableRow>
                  <TableRow key={`${c.column}-detail`}>
                    <TableCell colSpan={5} sx={{ p: 0, border: 0 }}>
                      <Collapse in={isOpen}>
                        <Box sx={{ bgcolor: '#FAFAFA', px: 3, py: 1.5,
                          borderTop: '1px solid #F1F1F1', borderBottom: '1px solid #F1F1F1' }}>
                          <Typography sx={{ fontSize: 11, fontWeight: 700,
                            color: '#6B7280', textTransform: 'uppercase',
                            letterSpacing: '0.08em', mb: 1 }}>
                            Sample changes (showing {c.samples.length})
                          </Typography>
                          <Table size="small">
                            <TableHead>
                              <TableRow sx={{ '& th': { fontSize: '0.7rem',
                                fontWeight: 700, color: '#6B7280' } }}>
                                <TableCell sx={{ width: 80 }}>Row</TableCell>
                                <TableCell>Before</TableCell>
                                <TableCell>After</TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {c.samples.map((s, i) => (
                                <TableRow key={i}>
                                  <TableCell sx={{ color: '#6B7280',
                                    fontVariantNumeric: 'tabular-nums' }}>
                                    {s.row}
                                  </TableCell>
                                  <TableCell sx={{ fontFamily: 'ui-monospace, Menlo, monospace',
                                    fontSize: '0.75rem', bgcolor: TONE.removed.bg,
                                    color: TONE.removed.fg, maxWidth: 360,
                                    whiteSpace: 'nowrap', overflow: 'hidden',
                                    textOverflow: 'ellipsis' }}>
                                    {String(s.before ?? '')}
                                  </TableCell>
                                  <TableCell sx={{ fontFamily: 'ui-monospace, Menlo, monospace',
                                    fontSize: '0.75rem', bgcolor: TONE.added.bg,
                                    color: TONE.added.fg, maxWidth: 360,
                                    whiteSpace: 'nowrap', overflow: 'hidden',
                                    textOverflow: 'ellipsis' }}>
                                    {String(s.after ?? '')}
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </Box>
                      </Collapse>
                    </TableCell>
                  </TableRow>
                </>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
}


function UnifiedDiffTable({ rows, columns, isFlagged, onlyChanged }) {
  const filteredRows = useMemo(() => {
    if (!onlyChanged) return rows;
    return rows.filter((r) => {
      if (r.row_status === 'added' || r.row_status === 'removed') return true;
      return columns.some((c) => isFlagged(r, c));
    });
  }, [rows, columns, isFlagged, onlyChanged]);

  if (filteredRows.length === 0) {
    return (
      <Alert severity="info" sx={{ mt: 2 }}>
        {onlyChanged
          ? 'No changed rows in the current window. Toggle off "Show only changed rows" to see all.'
          : 'No rows in the current window.'}
      </Alert>
    );
  }

  return (
    <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 600 }}>
      <Table size="small" stickyHeader>
        <TableHead>
          <TableRow>
            <TableCell sx={{
              width: 70, fontWeight: 700, fontSize: '0.7rem',
              color: '#6B7280', textTransform: 'uppercase',
              letterSpacing: '0.08em', bgcolor: '#FAFAFA',
              position: 'sticky', left: 0, zIndex: 3,
            }}>
              Row
            </TableCell>
            <TableCell sx={{
              width: 90, fontWeight: 700, fontSize: '0.7rem',
              color: '#6B7280', textTransform: 'uppercase',
              letterSpacing: '0.08em', bgcolor: '#FAFAFA',
            }}>
              Status
            </TableCell>
            {columns.map((c) => (
              <TableCell key={c} sx={{
                fontWeight: 700, fontSize: '0.7rem',
                color: '#6B7280', textTransform: 'uppercase',
                letterSpacing: '0.08em', bgcolor: '#FAFAFA',
              }}>
                {c}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {filteredRows.map((r) => {
            let statusChip = null;
            if (r.row_status === 'added') statusChip = { label: 'Added', tone: TONE.added };
            else if (r.row_status === 'removed') statusChip = { label: 'Removed', tone: TONE.removed };
            else if (columns.some((c) => isFlagged(r, c))) {
              statusChip = { label: 'Changed', tone: TONE.modified };
            } else {
              statusChip = { label: 'Unchanged', tone: TONE.neutral };
            }
            return (
              <TableRow key={r.row_index} hover>
                <TableCell sx={{
                  color: '#6B7280', fontWeight: 600,
                  fontVariantNumeric: 'tabular-nums',
                  position: 'sticky', left: 0, bgcolor: '#FFFFFF', zIndex: 2,
                }}>
                  {r.row_index}
                </TableCell>
                <TableCell>
                  <Chip size="small" label={statusChip.label}
                    sx={{ height: 20, fontSize: '0.66rem', fontWeight: 700,
                      bgcolor: statusChip.tone.bg, color: statusChip.tone.fg }} />
                </TableCell>
                {columns.map((c) => {
                  const flagged = isFlagged(r, c);
                  const before = r.original?.[c];
                  const after = r.modified?.[c];

                  if (r.row_status === 'removed') {
                    return (
                      <TableCell key={c} sx={{
                        fontFamily: 'ui-monospace, Menlo, monospace',
                        fontSize: '0.74rem',
                        bgcolor: TONE.removed.bg, color: TONE.removed.fg,
                        textDecoration: 'line-through',
                        maxWidth: 220, whiteSpace: 'nowrap',
                        overflow: 'hidden', textOverflow: 'ellipsis',
                      }}>
                        {String(before ?? '')}
                      </TableCell>
                    );
                  }
                  if (r.row_status === 'added') {
                    return (
                      <TableCell key={c} sx={{
                        fontFamily: 'ui-monospace, Menlo, monospace',
                        fontSize: '0.74rem',
                        bgcolor: TONE.added.bg, color: TONE.added.fg,
                        maxWidth: 220, whiteSpace: 'nowrap',
                        overflow: 'hidden', textOverflow: 'ellipsis',
                      }}>
                        {String(after ?? '')}
                      </TableCell>
                    );
                  }
                  if (flagged) {
                    return (
                      <TableCell key={c} sx={{
                        fontFamily: 'ui-monospace, Menlo, monospace',
                        fontSize: '0.74rem', p: '4px 8px',
                        maxWidth: 240, whiteSpace: 'nowrap',
                        overflow: 'hidden', textOverflow: 'ellipsis',
                      }}>
                        <Tooltip title={`Before: ${String(before ?? '')}`} arrow>
                          <Box>
                            <Box component="span" sx={{ display: 'inline-block',
                              px: 0.75, py: 0.125, borderRadius: 0.5,
                              bgcolor: TONE.removed.bg, color: TONE.removed.fg,
                              textDecoration: 'line-through', mr: 0.5,
                              fontSize: '0.7rem' }}>
                              {String(before ?? '')}
                            </Box>
                            <Box component="span" sx={{ display: 'inline-block',
                              px: 0.75, py: 0.125, borderRadius: 0.5,
                              bgcolor: TONE.added.bg, color: TONE.added.fg,
                              fontWeight: 600, fontSize: '0.7rem' }}>
                              {String(after ?? '')}
                            </Box>
                          </Box>
                        </Tooltip>
                      </TableCell>
                    );
                  }
                  return (
                    <TableCell key={c} sx={{
                      fontFamily: 'ui-monospace, Menlo, monospace',
                      fontSize: '0.74rem', color: '#475569',
                      maxWidth: 220, whiteSpace: 'nowrap',
                      overflow: 'hidden', textOverflow: 'ellipsis',
                    }}>
                      {String(after ?? '')}
                    </TableCell>
                  );
                })}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );
}


export default function Compare() {
  const { state, refresh } = useDataset();
  const [stats, setStats] = useState(null);
  const [byCol, setByCol] = useState(null);
  const [selectedCols, setSelectedCols] = useState([]);
  const [startRow, setStartRow] = useState(0);
  const [numRows, setNumRows] = useState(50);
  const [diff, setDiff] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const [onlyChanged, setOnlyChanged] = useState(true);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const loadStats = async () => {
    setErr('');
    try {
      const [statsRes, byColRes] = await Promise.all([
        api.get('/data/compare/stats'),
        api.get('/data/compare/by-column'),
      ]);
      setStats(statsRes.data);
      setByCol(byColRes.data);
      setSelectedCols((prev) => {
        if (prev.length > 0) return prev;
        // Default: pre-select the columns that actually changed (most useful)
        const touched = (byColRes.data?.columns || []).map((c) => c.column);
        if (touched.length > 0) return touched.slice(0, 8);
        return statsRes.data.common_columns.slice(0,
          Math.min(8, statsRes.data.common_columns.length));
      });
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Failed to load comparison stats');
    }
  };

  const loadDiff = async () => {
    if (!stats || selectedCols.length === 0) return;
    setLoading(true);
    try {
      const { data } = await api.get('/data/compare/cells', {
        params: { columns: selectedCols.join(','), start_row: startRow, num_rows: numRows },
      });
      setDiff(data);
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Failed to load diff');
    } finally { setLoading(false); }
  };

  useEffect(() => {
    if (state.loaded) loadStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.loaded, state.operations]);

  useEffect(() => {
    loadDiff();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stats, selectedCols.join(','), startRow, numRows]);

  const reset = async () => {
    if (!window.confirm('Reset all changes? This restores the working dataset to its original uploaded state.')) return;
    await api.post('/data/reset');
    await refresh();
    await loadStats();
  };

  const isFlagged = (row, col) => row.cell_flags?.[col] === 'modified';

  const maxStartRow = stats
    ? Math.max(0, Math.max(stats.original_rows, stats.modified_rows) - 1)
    : 0;

  const narrative = buildNarrative(stats, byCol);
  const removed = stats ? Math.max(0, stats.original_rows - stats.modified_rows) : 0;
  const removedPct = stats && stats.original_rows
    ? ((removed / stats.original_rows) * 100).toFixed(1)
    : '0.0';
  const cellsChanged = byCol?.total_modified_cells ?? stats?.modified_cells ?? 0;
  const cdesTouched = byCol?.cdes_touched ?? 0;

  if (!state.loaded) {
    return (
      <>
        <PageHeader title="Compare" />
        <EmptyState message="Load a dataset and make changes to use comparison." />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Before vs After"
        subtitle="Audit-grade view of what cleansing changed in your dataset"
        actions={
          <Button variant="outlined" startIcon={<RestartAltIcon />} onClick={reset}
            sx={{ textTransform: 'none', fontWeight: 600 }}>
            Reset to original
          </Button>
        } />

      {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}

      {(stats?.stale_state || byCol?.stale_state) && (
        <Alert
          severity="warning"
          sx={{ mb: 2 }}
          action={
            <Button color="inherit" size="small" onClick={reset}
              startIcon={<RestartAltIcon />}
              sx={{ textTransform: 'none', fontWeight: 700 }}>
              Reset & re-cleanse
            </Button>
          }
        >
          <Typography sx={{ fontWeight: 700, fontSize: 14, mb: 0.5 }}>
            This diff is showing stale alignment.
          </Typography>
          <Typography sx={{ fontSize: 12.5 }}>
            Your dataset was cleansed with an earlier version of the tool that
            re-indexed rows after dropping them. Row identity is lost, so the
            "Changed" badges below may not reflect real edits — they're side-effects
            of the broken alignment. <b>Click "Reset & re-cleanse"</b> to restore the
            original dataset, then re-apply your rules. Future cleansing actions
            will preserve row identity correctly.
          </Typography>
        </Alert>
      )}

      {/* ── Narrative summary ────────────────────────────────────── */}
      {stats && (
        <Paper variant="outlined" sx={{ p: 2.5, mb: 2.5, borderRadius: 2,
          background: 'linear-gradient(180deg, #FFFFFF 0%, #FAFAFC 100%)' }}>
          <Typography sx={{ fontSize: 14, fontWeight: 700, color: '#6B7280',
            textTransform: 'uppercase', letterSpacing: '0.08em', mb: 0.75 }}>
            Cleansing impact
          </Typography>
          <Typography sx={{ fontSize: 16, fontWeight: 500, color: '#1A1A1A',
            lineHeight: 1.5, mb: 2 }}>
            {narrative}
          </Typography>

          <Grid container spacing={1.5}>
            <Grid item xs={12} sm={6} md={3}>
              <HeroKPI
                label="Original rows"
                value={stats.original_rows.toLocaleString()}
                sub="As uploaded"
              />
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <HeroKPI
                label="Current rows"
                value={stats.modified_rows.toLocaleString()}
                sub={removed > 0 ? `${removed.toLocaleString()} removed (${removedPct}%)` : 'No rows removed'}
                accent={removed > 0 ? '#b91c1c' : undefined}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <HeroKPI
                label="Cells modified"
                value={cellsChanged.toLocaleString()}
                sub={cdesTouched > 0 ? `Across ${cdesTouched} CDE${cdesTouched === 1 ? '' : 's'}` : 'No edits'}
                accent={cellsChanged > 0 ? '#854d0e' : undefined}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <HeroKPI
                label="CDEs in dataset"
                value={stats.modified_columns}
                sub={`${stats.common_columns.length} present in both views`}
              />
            </Grid>
          </Grid>
        </Paper>
      )}

      {/* ── Per-CDE change ledger ────────────────────────────────── */}
      <ChangeLedger byCol={byCol} />

      {/* ── Detail view (row-by-row diff) ────────────────────────── */}
      {stats && stats.common_columns.length > 0 && (
        <Paper variant="outlined" sx={{ borderRadius: 2 }}>
          <Box sx={{ px: 2.5, py: 1.75, borderBottom: '1px solid #E5E7EB',
            display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
            <Typography sx={{ fontSize: 15, fontWeight: 700, color: '#1A1A1A',
              flex: 1 }}>
              Row-by-row diff
            </Typography>
            <ToggleButtonGroup
              size="small"
              value={onlyChanged ? 'changed' : 'all'}
              exclusive
              onChange={(_, v) => v && setOnlyChanged(v === 'changed')}
            >
              <ToggleButton value="changed" sx={{ textTransform: 'none', fontSize: '0.78rem' }}>
                Only changed rows
              </ToggleButton>
              <ToggleButton value="all" sx={{ textTransform: 'none', fontSize: '0.78rem' }}>
                All rows
              </ToggleButton>
            </ToggleButtonGroup>
            <Button
              size="small"
              startIcon={<TuneIcon />}
              onClick={() => setShowAdvanced((v) => !v)}
              sx={{ textTransform: 'none', fontWeight: 600, color: '#6B7280' }}>
              {showAdvanced ? 'Hide filters' : 'Filters'}
            </Button>
          </Box>

          <Collapse in={showAdvanced}>
            <Box sx={{ px: 2.5, py: 2, bgcolor: '#FAFAFA', borderBottom: '1px solid #E5E7EB' }}>
              <Grid container spacing={2}>
                <Grid item xs={12} md={6}>
                  <FormControl fullWidth size="small">
                    <InputLabel>Critical data elements</InputLabel>
                    <Select multiple value={selectedCols}
                      onChange={(e) => setSelectedCols(typeof e.target.value === 'string'
                        ? e.target.value.split(',') : e.target.value)}
                      input={<OutlinedInput label="Critical data elements" />}
                      renderValue={(s) => `${s.length} selected`}>
                      {stats.common_columns.map((c) => (
                        <MenuItem key={c} value={c}>{c}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={6} md={3}>
                  <TextField fullWidth size="small" type="number" label="Start row"
                    value={startRow}
                    onChange={(e) => {
                      const v = parseInt(e.target.value || '0', 10);
                      setStartRow(Math.max(0, Math.min(maxStartRow, v)));
                    }}
                    inputProps={{ min: 0, max: maxStartRow }} />
                </Grid>
                <Grid item xs={6} md={3}>
                  <TextField fullWidth size="small" type="number" label="Rows to scan"
                    value={numRows}
                    onChange={(e) => {
                      const v = parseInt(e.target.value || '50', 10);
                      setNumRows(Math.max(1, Math.min(500, v)));
                    }}
                    inputProps={{ min: 1, max: 500 }} />
                </Grid>
              </Grid>
            </Box>
          </Collapse>

          {loading && <LinearProgress />}

          <Box sx={{ p: 2 }}>
            {diff && diff.rows && diff.rows.length > 0 && selectedCols.length > 0 ? (
              <UnifiedDiffTable
                rows={diff.rows}
                columns={selectedCols}
                isFlagged={isFlagged}
                onlyChanged={onlyChanged}
              />
            ) : selectedCols.length === 0 ? (
              <Alert severity="warning">Pick at least one CDE under Filters to see the row diff.</Alert>
            ) : (
              <Alert severity="info">Loading diff…</Alert>
            )}
          </Box>
        </Paper>
      )}

      {stats && stats.common_columns.length === 0 && (
        <Alert severity="warning">
          No common critical data elements between the original and current dataset.
        </Alert>
      )}
    </>
  );
}
