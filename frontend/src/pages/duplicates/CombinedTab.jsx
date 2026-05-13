import { useState } from 'react';
import {
  Box, Grid, FormControl, InputLabel, Select, MenuItem, OutlinedInput,
  Button, Typography, Alert, LinearProgress, Slider,
} from '@mui/material';
import api from '../../api.js';
import DuplicateResults from './DuplicateResults.jsx';

const ALGORITHMS = ['rapidfuzz', 'jaro_winkler', 'metaphone', 'combined'];

export default function CombinedTab({ allColumns, objectColumns }) {
  const [exactCols, setExactCols] = useState([]);
  const [fuzzyCols, setFuzzyCols] = useState([]);
  const [threshold, setThreshold] = useState(85);
  const [algorithm, setAlgorithm] = useState('rapidfuzz');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [result, setResult] = useState(null);

  const scan = async () => {
    setBusy(true); setErr(''); setResult(null);
    try {
      const { data } = await api.post('/duplicates/combined/scan', {
        exact_columns: exactCols, fuzzy_columns: fuzzyCols, threshold, algorithm,
      });
      setResult(data);
    } catch (e) { setErr(e?.response?.data?.detail || 'Scan failed'); }
    finally { setBusy(false); }
  };

  return (
    <Box>
      <Typography variant="h5" gutterBottom>Combined Duplicate Detection</Typography>
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={6}>
          <FormControl fullWidth size="small">
            <InputLabel>Exact match critical data elements</InputLabel>
            <Select multiple value={exactCols}
              onChange={(e) => setExactCols(typeof e.target.value === 'string' ? e.target.value.split(',') : e.target.value)}
              input={<OutlinedInput label="Exact match critical data elements" />}
              renderValue={(s) => s.join(', ')}>
              {allColumns.map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
            </Select>
          </FormControl>
        </Grid>
        <Grid item xs={12} md={6}>
          <FormControl fullWidth size="small">
            <InputLabel>Fuzzy match critical data elements</InputLabel>
            <Select multiple value={fuzzyCols}
              onChange={(e) => setFuzzyCols(typeof e.target.value === 'string' ? e.target.value.split(',') : e.target.value)}
              input={<OutlinedInput label="Fuzzy match critical data elements" />}
              renderValue={(s) => s.join(', ')}>
              {objectColumns.map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
            </Select>
          </FormControl>
        </Grid>
      </Grid>

      <Box sx={{ px: 1, mb: 2 }}>
        <Typography variant="caption">Fuzzy Threshold: <b>{threshold}%</b></Typography>
        <Slider value={threshold} onChange={(_, v) => setThreshold(v)} min={50} max={100} step={1} />
      </Box>

      <FormControl size="small" sx={{ minWidth: 240, mb: 2 }}>
        <InputLabel>Algorithm</InputLabel>
        <Select value={algorithm} label="Algorithm" onChange={(e) => setAlgorithm(e.target.value)}>
          {ALGORITHMS.map((a) => <MenuItem key={a} value={a}>{a}</MenuItem>)}
        </Select>
      </FormControl>

      <Button variant="contained" disabled={busy} onClick={scan} fullWidth sx={{ mb: 2 }}>
        Scan for Combined Duplicates
      </Button>

      {busy && <LinearProgress sx={{ mb: 2 }} />}
      {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}

      {result && result.total_groups === 0 && (
        <Alert severity="info">No combined duplicates found</Alert>
      )}

      {result && result.total_groups > 0 && (
        <DuplicateResults
          dupType="combined"
          summaries={result.summaries}
          totalGroups={result.total_groups}
          totalRows={result.total_rows}
          onScanAgain={scan}
          removeAllControls={
            <Alert severity="info" sx={{ height: '100%', display: 'flex', alignItems: 'center' }}>
              Bulk remove not available for combined. Use group actions.
            </Alert>
          }
        />
      )}
    </Box>
  );
}
