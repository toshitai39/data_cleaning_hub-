import { useEffect, useState } from 'react';
import {
  Box, Stack, Typography, TextField, Button, MenuItem, Alert, LinearProgress,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper, Divider,
} from '@mui/material';
import api from '../../api.js';

export default function DriftTab() {
  const [name, setName] = useState('');
  const [baselines, setBaselines] = useState([]);
  const [delPick, setDelPick] = useState('');
  const [comparePick, setComparePick] = useState('');
  const [nullThr, setNullThr] = useState(5.0);
  const [uniqThr, setUniqThr] = useState(10.0);
  const [meanThr, setMeanThr] = useState(2.0);
  const [alerts, setAlerts] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  const refresh = () => {
    api.get('/profile/drift/baselines')
      .then((r) => setBaselines(r.data))
      .catch(() => setBaselines([]));
  };
  useEffect(refresh, []);

  const save = async () => {
    if (!name.trim()) return;
    setBusy(true); setErr(''); setMsg('');
    try {
      await api.post('/profile/drift/save-baseline', { name });
      setMsg(`Baseline '${name}' saved`);
      setName('');
      refresh();
    } catch (e) { setErr(e?.response?.data?.detail || 'Failed'); }
    finally { setBusy(false); }
  };

  const remove = async () => {
    if (!delPick) return;
    setBusy(true); setErr('');
    try {
      await api.delete(`/profile/drift/baselines/${encodeURIComponent(delPick)}`);
      setMsg(`Deleted '${delPick}'`);
      setDelPick('');
      refresh();
    } catch (e) { setErr(e?.response?.data?.detail || 'Failed'); }
    finally { setBusy(false); }
  };

  const detect = async () => {
    if (!comparePick) return;
    setBusy(true); setErr(''); setMsg('');
    try {
      const { data } = await api.post('/profile/drift/detect', {
        baseline_name: comparePick,
        null_threshold: nullThr,
        unique_threshold: uniqThr,
        mean_std_threshold: meanThr,
      });
      setAlerts(data);
    } catch (e) { setErr(e?.response?.data?.detail || 'Failed'); }
    finally { setBusy(false); }
  };

  return (
    <Box>
      <Typography variant="h5" gutterBottom>Data Drift Detection</Typography>
      <Typography variant="body2" color="text.secondary" mb={2}>
        Save the current profile as a baseline, then compare future datasets against it.
      </Typography>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} mb={2}>
        <TextField label="Baseline name" size="small" value={name}
          onChange={(e) => setName(e.target.value)} sx={{ flex: 2 }} />
        <Button variant="contained" onClick={save} disabled={busy}>Save Current as Baseline</Button>
        {baselines.length > 0 && (
          <>
            <TextField select label="Delete baseline" size="small" value={delPick}
              onChange={(e) => setDelPick(e.target.value)} sx={{ flex: 1, minWidth: 180 }}>
              {baselines.map((b) => <MenuItem key={b.name} value={b.name}>{b.name}</MenuItem>)}
            </TextField>
            <Button variant="outlined" color="error" onClick={remove} disabled={busy || !delPick}>Delete</Button>
          </>
        )}
      </Stack>

      {busy && <LinearProgress sx={{ mb: 2 }} />}
      {msg && <Alert severity="success" sx={{ mb: 2 }}>{msg}</Alert>}
      {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}

      <Divider sx={{ my: 2 }} />

      {baselines.length > 0 ? (
        <>
          <TextField select label="Compare against baseline" size="small" value={comparePick}
            onChange={(e) => setComparePick(e.target.value)} sx={{ minWidth: 240, mb: 2 }}>
            {baselines.map((b) => <MenuItem key={b.name} value={b.name}>{b.name}</MenuItem>)}
          </TextField>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} mb={2}>
            <TextField label="Null % threshold" type="number" size="small" value={nullThr}
              onChange={(e) => setNullThr(parseFloat(e.target.value))}
              inputProps={{ step: 1, min: 0.1 }} />
            <TextField label="Unique % threshold" type="number" size="small" value={uniqThr}
              onChange={(e) => setUniqThr(parseFloat(e.target.value))}
              inputProps={{ step: 1, min: 0.1 }} />
            <TextField label="Mean shift (sigma)" type="number" size="small" value={meanThr}
              onChange={(e) => setMeanThr(parseFloat(e.target.value))}
              inputProps={{ step: 0.5, min: 0.1 }} />
          </Stack>
          <Button variant="contained" onClick={detect} disabled={busy || !comparePick}>
            Run Drift Detection
          </Button>

          {alerts !== null && (
            alerts.length === 0 ? (
              <Alert severity="success" sx={{ mt: 2 }}>No significant drift detected.</Alert>
            ) : (
              <>
                <Alert severity="warning" sx={{ mt: 2, mb: 1 }}>
                  {alerts.length} drift alert(s) detected
                </Alert>
                <TableContainer component={Paper}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        {Object.keys(alerts[0] || {}).map((c) => (
                          <TableCell key={c} sx={{ fontWeight: 600 }}>{c}</TableCell>
                        ))}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {alerts.map((row, i) => (
                        <TableRow key={i}>
                          {Object.entries(row).map(([k, v]) => (
                            <TableCell key={k}>{String(v)}</TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </>
            )
          )}
        </>
      ) : (
        <Alert severity="info">No baselines saved yet. Save one above to enable drift detection.</Alert>
      )}
    </Box>
  );
}
