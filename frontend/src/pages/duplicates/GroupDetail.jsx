import { useEffect, useState } from 'react';
import {
  Box, Grid, Stack, Typography, Button, Alert, LinearProgress, Checkbox,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper, Chip,
} from '@mui/material';
import api from '../../api.js';

export default function GroupDetail({ dupType, groupId, onChanged }) {
  const [group, setGroup] = useState(null);
  const [picked, setPicked] = useState({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  useEffect(() => {
    setErr(''); setGroup(null); setPicked({});
    api.get(`/duplicates/${dupType}/group/${groupId}`)
      .then((r) => setGroup(r.data))
      .catch((e) => setErr(e?.response?.data?.detail || 'Failed'));
  }, [dupType, groupId]);

  const togglePick = (i) => setPicked((p) => ({ ...p, [i]: !p[i] }));

  const remove = async (strategy, opts = {}) => {
    setBusy(true); setErr('');
    try {
      await api.post(`/duplicates/${dupType}/remove-group/${groupId}`, {
        strategy, ...opts,
      });
      onChanged?.();
    } catch (e) { setErr(e?.response?.data?.detail || 'Failed'); }
    finally { setBusy(false); }
  };

  if (err) return <Alert severity="error">{err}</Alert>;
  if (!group) return <LinearProgress />;

  const selectedRows = Object.entries(picked).filter(([_, v]) => v).map(([k]) => parseInt(k, 10));

  const cols = group.values.length > 0 ? Object.keys(group.values[0]) : [];

  return (
    <Box>
      {/* Group metadata */}
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={4}>
          <Paper sx={{ p: 2, textAlign: 'center' }}>
            <Typography variant="caption" color="text.secondary">Rows in Group</Typography>
            <Typography variant="h6">{group.rows}</Typography>
          </Paper>
        </Grid>
        <Grid item xs={4}>
          <Paper sx={{ p: 2, textAlign: 'center' }}>
            <Typography variant="caption" color="text.secondary">Similarity</Typography>
            <Typography variant="h6">{group.similarity.toFixed(1)}%</Typography>
          </Paper>
        </Grid>
        <Grid item xs={4}>
          <Paper sx={{ p: 2, textAlign: 'center' }}>
            <Typography variant="caption" color="text.secondary">Match Type</Typography>
            <Typography variant="h6">{group.match_type}</Typography>
          </Paper>
        </Grid>
      </Grid>

      {group.key_columns?.length > 0 && (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5 }}>
          <b>Key critical data elements:</b> {group.key_columns.join(', ')}
        </Typography>
      )}

      {/* Rows table with Keep checkboxes */}
      <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 420 }}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 600, width: 60 }}>Keep</TableCell>
              {cols.map((c) => (
                <TableCell key={c} sx={{ fontWeight: 600 }}>{c}</TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {group.values.map((row, i) => (
              <TableRow key={i}>
                <TableCell>
                  <Checkbox size="small" checked={!!picked[i]} onChange={() => togglePick(i)} />
                </TableCell>
                {cols.map((c) => (
                  <TableCell key={c} sx={{ fontFamily: 'monospace', fontSize: '0.78rem' }}>
                    {row[c] == null ? '' : String(row[c])}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      {selectedRows.length > 0 && (
        <Alert severity="success" sx={{ mt: 1 }}>
          {selectedRows.length} row(s) selected to keep
        </Alert>
      )}

      {busy && <LinearProgress sx={{ mt: 1 }} />}

      {/* Action buttons */}
      <Grid container spacing={1.5} sx={{ mt: 1 }}>
        <Grid item xs={12} sm={3}>
          <Button fullWidth variant="outlined" disabled={busy} onClick={() => remove('keep_first')}>
            Keep First
          </Button>
        </Grid>
        <Grid item xs={12} sm={3}>
          <Button fullWidth variant="outlined" disabled={busy} onClick={() => remove('keep_last')}>
            Keep Last
          </Button>
        </Grid>
        <Grid item xs={12} sm={3}>
          <Button fullWidth variant="contained" disabled={busy || selectedRows.length === 0}
            onClick={() => {
              if (selectedRows.length === 1) {
                remove('keep_selected', { selected_index: selectedRows[0] });
              } else {
                remove('keep_multiple', { selected_indices: selectedRows });
              }
            }}>
            Keep Selected
          </Button>
        </Grid>
        <Grid item xs={12} sm={3}>
          <Button fullWidth variant="outlined" disabled={busy} onClick={() => remove('merge')}>
            Merge
          </Button>
        </Grid>
      </Grid>
    </Box>
  );
}
