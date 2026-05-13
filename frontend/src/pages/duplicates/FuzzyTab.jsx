import { useState } from 'react';
import {
  Box, Grid, FormControl, InputLabel, Select, MenuItem, OutlinedInput,
  Button, Typography, Alert, LinearProgress, Slider,
} from '@mui/material';
import api from '../../api.js';
import DuplicateResults from './DuplicateResults.jsx';

const ALGORITHMS = ['rapidfuzz', 'jaro_winkler', 'metaphone', 'combined'];

export default function FuzzyTab({ objectColumns }) {
  const [columns, setColumns] = useState([]);
  const [threshold, setThreshold] = useState(85);
  const [algorithm, setAlgorithm] = useState('rapidfuzz');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [warn, setWarn] = useState('');
  const [result, setResult] = useState(null);

  const scan = async () => {
    if (columns.length === 0) {
      setWarn('Please select at least one column');
      return;
    }
    setBusy(true); setErr(''); setWarn(''); setResult(null);
    try {
      const { data } = await api.post('/duplicates/fuzzy/scan', {
        columns, threshold, algorithm,
      });
      setResult(data);
    } catch (e) { setErr(e?.response?.data?.detail || 'Scan failed'); }
    finally { setBusy(false); }
  };

  return (
    <Box>
      <Typography variant="h5" gutterBottom>Fuzzy Duplicate Detection</Typography>
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={4}>
          <FormControl fullWidth size="small">
            <InputLabel>Critical data elements to scan</InputLabel>
            <Select multiple value={columns}
              onChange={(e) => setColumns(typeof e.target.value === 'string' ? e.target.value.split(',') : e.target.value)}
              input={<OutlinedInput label="Critical data elements to scan" />}
              renderValue={(s) => s.join(', ')}>
              {objectColumns.map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
            </Select>
          </FormControl>
        </Grid>
        <Grid item xs={12} md={4}>
          <Box sx={{ px: 1 }}>
            <Typography variant="caption">Similarity Threshold: <b>{threshold}%</b></Typography>
            <Slider value={threshold} onChange={(_, v) => setThreshold(v)} min={50} max={100} step={1} />
          </Box>
        </Grid>
        <Grid item xs={12} md={4}>
          <FormControl fullWidth size="small">
            <InputLabel>Algorithm</InputLabel>
            <Select value={algorithm} label="Algorithm" onChange={(e) => setAlgorithm(e.target.value)}>
              {ALGORITHMS.map((a) => <MenuItem key={a} value={a}>{a}</MenuItem>)}
            </Select>
          </FormControl>
        </Grid>
      </Grid>

      <Button variant="contained" disabled={busy} onClick={scan} fullWidth sx={{ mb: 2 }}>
        Scan for Fuzzy Duplicates
      </Button>

      {busy && <LinearProgress sx={{ mb: 2 }} />}
      {warn && <Alert severity="warning" sx={{ mb: 2 }}>{warn}</Alert>}
      {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}

      {result && result.total_groups === 0 && (
        <Alert severity="info">No fuzzy duplicates found</Alert>
      )}

      {result && result.total_groups > 0 && (
        <DuplicateResults
          dupType="fuzzy"
          summaries={result.summaries}
          totalGroups={result.total_groups}
          totalRows={result.total_rows}
          onScanAgain={scan}
          removeAllControls={
            <Alert severity="info" sx={{ height: '100%', display: 'flex', alignItems: 'center' }}>
              Bulk remove not available for fuzzy. Use group actions below.
            </Alert>
          }
        />
      )}
    </Box>
  );
}
