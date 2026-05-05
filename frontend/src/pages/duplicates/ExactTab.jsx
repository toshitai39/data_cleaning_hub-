import { useState } from 'react';
import {
  Box, Grid, FormControl, InputLabel, Select, MenuItem, OutlinedInput,
  Button, Typography, Alert, LinearProgress, Stack,
} from '@mui/material';
import api from '../../api.js';
import DuplicateResults from './DuplicateResults.jsx';

const KEEP_OPTIONS = ['first', 'last', 'none'];

export default function ExactTab({ allColumns }) {
  const [subset, setSubset] = useState([]);
  const [keep, setKeep] = useState('first');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [result, setResult] = useState(null);

  const scan = async () => {
    setBusy(true); setErr(''); setResult(null);
    try {
      const { data } = await api.post('/duplicates/exact/scan', {
        subset: subset.length ? subset : null,
      });
      setResult(data);
    } catch (e) { setErr(e?.response?.data?.detail || 'Scan failed'); }
    finally { setBusy(false); }
  };

  const removeAll = async () => {
    setBusy(true); setErr('');
    try {
      const { data } = await api.post('/duplicates/exact/remove-all', {
        subset: subset.length ? subset : null, keep,
      });
      setResult(null);
      setErr(''); // clear; show success below
      alert(`Removed ${data.removed} rows. ${data.rows_remaining} remaining.`);
    } catch (e) { setErr(e?.response?.data?.detail || 'Failed'); }
    finally { setBusy(false); }
  };

  return (
    <Box>
      <Typography variant="h5" gutterBottom>Exact Duplicate Detection</Typography>
      <Grid container spacing={2} alignItems="center" sx={{ mb: 2 }}>
        <Grid item xs={12} md={6}>
          <FormControl fullWidth size="small">
            <InputLabel>Check specific columns (empty = all)</InputLabel>
            <Select multiple value={subset}
              onChange={(e) => setSubset(typeof e.target.value === 'string' ? e.target.value.split(',') : e.target.value)}
              input={<OutlinedInput label="Check specific columns (empty = all)" />}
              renderValue={(s) => s.join(', ')}>
              {allColumns.map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
            </Select>
          </FormControl>
        </Grid>
        <Grid item xs={6} md={3}>
          <FormControl fullWidth size="small">
            <InputLabel>Keep strategy</InputLabel>
            <Select value={keep} label="Keep strategy" onChange={(e) => setKeep(e.target.value)}>
              {KEEP_OPTIONS.map((k) => <MenuItem key={k} value={k}>{k}</MenuItem>)}
            </Select>
          </FormControl>
        </Grid>
        <Grid item xs={6} md={3}>
          <Button fullWidth variant="contained" disabled={busy} onClick={scan}>
            Scan for Exact Duplicates
          </Button>
        </Grid>
      </Grid>

      {busy && <LinearProgress sx={{ mb: 2 }} />}
      {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}

      {result && result.total_groups === 0 && (
        <Alert severity="success">No exact duplicates found</Alert>
      )}

      {result && result.total_groups > 0 && (
        <DuplicateResults
          dupType="exact"
          summaries={result.summaries}
          totalGroups={result.total_groups}
          totalRows={result.total_rows}
          onScanAgain={scan}
          removeAllControls={
            <Button fullWidth variant="outlined" color="error" sx={{ height: '100%' }} onClick={removeAll}>
              Remove All Duplicates
            </Button>
          }
        />
      )}
    </Box>
  );
}
