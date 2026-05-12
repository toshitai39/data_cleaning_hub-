import { useEffect, useMemo, useState } from 'react';
import {
  Box, Grid, Paper, Typography, Stack, Button, Alert, LinearProgress,
  TextField, MenuItem, OutlinedInput, FormControl, InputLabel, Select,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Divider,
} from '@mui/material';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import api from '../api.js';
import PageHeader from '../components/PageHeader.jsx';
import EmptyState from '../components/EmptyState.jsx';
import { useDataset } from '../context/DatasetContext.jsx';

// 1:1 colour palette from features/compare/ui.py
const COLORS = {
  modified: '#fef3c7',  // yellow
  added:    '#d1fae5',  // green
  removed:  '#fee2e2',  // red
};

function StatItem({ label, value, sign = false }) {
  let color = '#1f2937';
  if (sign && typeof value === 'number') {
    if (value > 0) color = '#10b981';
    else if (value < 0) color = '#ef4444';
  }
  const display = sign && typeof value === 'number'
    ? `${value > 0 ? '+' : ''}${value.toLocaleString()}`
    : (typeof value === 'number' ? value.toLocaleString() : value);
  return (
    <Box sx={{ textAlign: 'center', flex: 1, minWidth: 110 }}>
      <Typography variant="caption" sx={{
        color: '#6b7280', textTransform: 'uppercase', letterSpacing: 0.5, fontSize: '0.72rem',
      }}>{label}</Typography>
      <Typography sx={{ fontSize: '1.4rem', fontWeight: 700, color, mt: 0.25 }}>
        {display}
      </Typography>
    </Box>
  );
}

function DiffPanel({ title, accent, columns, rows, side, isFlagged }) {
  // side: 'original' | 'modified' — picks which column of the diff row to render
  return (
    <Paper sx={{ borderLeft: `4px solid ${accent}`, p: 2, height: '100%' }}>
      <Typography sx={{
        fontSize: '1rem', fontWeight: 700, mb: 1.5, pb: 1,
        borderBottom: '2px solid #e5e7eb', letterSpacing: 0.5,
      }}>
        {title}
      </Typography>
      <TableContainer sx={{ maxHeight: 600 }}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 600, bgcolor: '#FBFAFC', width: 60 }}>Row</TableCell>
              {columns.map((c) => (
                <TableCell key={c} sx={{ fontWeight: 600, bgcolor: '#FBFAFC' }}>{c}</TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((r) => {
              const data = r[side];
              // Determine row-level styling
              let rowBg = 'inherit';
              if (side === 'original' && r.row_status === 'removed') rowBg = COLORS.removed;
              if (side === 'modified' && r.row_status === 'added') rowBg = COLORS.added;
              return (
                <TableRow key={r.row_index} sx={{ bgcolor: rowBg }}>
                  <TableCell sx={{ color: '#64748b', fontWeight: 600 }}>{r.row_index}</TableCell>
                  {columns.map((c) => {
                    let cellBg = 'inherit';
                    let cellWeight = 'normal';
                    // Cell-level highlighting only on the modified panel for "modified" cells.
                    if (side === 'modified' && isFlagged(r, c)) {
                      cellBg = COLORS.modified; cellWeight = 700;
                    }
                    const v = data ? data[c] : null;
                    return (
                      <TableCell key={c} sx={{
                        bgcolor: cellBg, fontWeight: cellWeight,
                        fontFamily: 'monospace', fontSize: '0.78rem',
                      }}>
                        {data == null ? '' : (v == null ? '' : String(v))}
                      </TableCell>
                    );
                  })}
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
}

function Legend() {
  return (
    <Box sx={{
      mt: 2.5, p: 2, bgcolor: '#f9fafb', borderRadius: 2,
      display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap',
    }}>
      <Typography sx={{ fontWeight: 700 }}>Legend:</Typography>
      <Box sx={{ px: 1.5, py: 0.5, bgcolor: COLORS.modified, borderRadius: 1 }}>Modified Value</Box>
      <Box sx={{ px: 1.5, py: 0.5, bgcolor: COLORS.added, borderRadius: 1 }}>New Row</Box>
      <Box sx={{ px: 1.5, py: 0.5, bgcolor: COLORS.removed, borderRadius: 1 }}>Removed Row</Box>
    </Box>
  );
}

export default function Compare() {
  const { state, refresh } = useDataset();
  const [stats, setStats] = useState(null);
  const [selectedCols, setSelectedCols] = useState([]);
  const [startRow, setStartRow] = useState(0);
  const [numRows, setNumRows] = useState(50);
  const [diff, setDiff] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');

  const loadStats = async () => {
    setErr('');
    try {
      const { data } = await api.get('/data/compare/stats');
      setStats(data);
      // Default: first 10 common columns (matches Streamlit default)
      setSelectedCols((prev) => {
        if (prev.length > 0) return prev;
        return data.common_columns.slice(0, Math.min(10, data.common_columns.length));
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
    await api.post('/data/reset');
    await refresh();
    await loadStats();
  };

  const isFlagged = (row, col) => row.cell_flags?.[col] === 'modified';

  const maxStartRow = stats
    ? Math.max(0, Math.max(stats.original_rows, stats.modified_rows) - 1)
    : 0;

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
      <PageHeader title="Compare: Original vs Modified"
        actions={
          <Button variant="outlined" startIcon={<RestartAltIcon />} onClick={reset}>
            Reset to Original
          </Button>
        } />

      {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}

      {/* Stat row — verbatim port of the 7-stat summary */}
      {stats && (
        <Paper sx={{ p: 2, mb: 2, bgcolor: '#f9fafb' }}>
          <Stack direction="row" justifyContent="space-around" flexWrap="wrap"
            useFlexGap spacing={1.5}>
            <StatItem label="Original Rows" value={stats.original_rows} />
            <StatItem label="Modified Rows" value={stats.modified_rows} />
            <StatItem label="Row Change" value={stats.row_change} sign />
            <StatItem label="Original Columns" value={stats.original_columns} />
            <StatItem label="Modified Columns" value={stats.modified_columns} />
            <StatItem label="Column Change" value={stats.column_change} sign />
            <StatItem label="Modified Cells" value={stats.modified_cells}
              sign={false} />
          </Stack>
        </Paper>
      )}

      <Divider sx={{ my: 2 }} />

      {/* Settings row */}
      {stats && stats.common_columns.length > 0 && (
        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid item xs={12} md={6}>
            <FormControl fullWidth size="small">
              <InputLabel>Select columns to compare</InputLabel>
              <Select multiple value={selectedCols}
                onChange={(e) => setSelectedCols(typeof e.target.value === 'string'
                  ? e.target.value.split(',') : e.target.value)}
                input={<OutlinedInput label="Select columns to compare" />}
                renderValue={(s) => s.join(', ')}>
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
            <TextField fullWidth size="small" type="number" label="Rows to show"
              value={numRows}
              onChange={(e) => {
                const v = parseInt(e.target.value || '50', 10);
                setNumRows(Math.max(1, Math.min(500, v)));
              }}
              inputProps={{ min: 1, max: 500 }} />
          </Grid>
        </Grid>
      )}

      {stats && stats.common_columns.length === 0 && (
        <Alert severity="warning">No common columns found between original and modified data</Alert>
      )}

      {selectedCols.length === 0 && stats && stats.common_columns.length > 0 && (
        <Alert severity="warning">Please select at least one column to compare</Alert>
      )}

      {loading && <LinearProgress sx={{ mb: 2 }} />}

      {/* Side-by-side diff panels */}
      {diff && diff.rows && diff.rows.length > 0 && selectedCols.length > 0 && (
        <>
          <Grid container spacing={2}>
            <Grid item xs={12} md={6}>
              <DiffPanel title="ORIGINAL DATA" accent="#3b82f6"
                columns={selectedCols} rows={diff.rows}
                side="original" isFlagged={isFlagged} />
            </Grid>
            <Grid item xs={12} md={6}>
              <DiffPanel title="MODIFIED DATA" accent="#10b981"
                columns={selectedCols} rows={diff.rows}
                side="modified" isFlagged={isFlagged} />
            </Grid>
          </Grid>

          <Legend />

          {diff.changes_found && (
            <>
              <Divider sx={{ my: 3 }} />
              <Typography variant="h6" gutterBottom>Change Summary</Typography>
              <Grid container spacing={2}>
                <Grid item xs={4}>
                  <Paper sx={{ p: 2, textAlign: 'center' }}>
                    <Typography variant="caption" color="text.secondary"
                      sx={{ textTransform: 'uppercase', letterSpacing: 0.6 }}>
                      Modified Cells
                    </Typography>
                    <Typography variant="h5" sx={{ fontWeight: 700,
                      color: diff.modified_cells > 0 ? '#d97706' : 'text.primary' }}>
                      {diff.modified_cells}
                    </Typography>
                  </Paper>
                </Grid>
                <Grid item xs={4}>
                  <Paper sx={{ p: 2, textAlign: 'center' }}>
                    <Typography variant="caption" color="text.secondary"
                      sx={{ textTransform: 'uppercase', letterSpacing: 0.6 }}>
                      Added Rows
                    </Typography>
                    <Typography variant="h5" sx={{ fontWeight: 700,
                      color: diff.added_rows > 0 ? '#10b981' : 'text.primary' }}>
                      {diff.added_rows}
                    </Typography>
                  </Paper>
                </Grid>
                <Grid item xs={4}>
                  <Paper sx={{ p: 2, textAlign: 'center' }}>
                    <Typography variant="caption" color="text.secondary"
                      sx={{ textTransform: 'uppercase', letterSpacing: 0.6 }}>
                      Removed Rows
                    </Typography>
                    <Typography variant="h5" sx={{ fontWeight: 700,
                      color: diff.removed_rows > 0 ? '#ef4444' : 'text.primary' }}>
                      {diff.removed_rows}
                    </Typography>
                  </Paper>
                </Grid>
              </Grid>
            </>
          )}
        </>
      )}
    </>
  );
}
