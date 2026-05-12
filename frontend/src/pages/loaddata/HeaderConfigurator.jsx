import { useEffect, useState } from 'react';
import {
  Box, Grid, TextField, MenuItem, Button, Typography, Alert, LinearProgress,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper,
} from '@mui/material';
import api from '../../api.js';

export default function HeaderConfigurator({ stagedFile, onLoaded }) {
  const [sheetName, setSheetName] = useState(stagedFile.sheets?.[0] || '');
  const [headerRow, setHeaderRow] = useState(0);
  const [previewRows, setPreviewRows] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const fetchPreview = async (sheet) => {
    setBusy(true); setErr('');
    try {
      const { data } = await api.get('/data/raw-preview', {
        params: { n_rows: 20, sheet_name: sheet || undefined },
      });
      setPreviewRows(data.rows || []);
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Preview failed');
    } finally { setBusy(false); }
  };

  useEffect(() => { fetchPreview(sheetName); /* eslint-disable-next-line */ }, [sheetName]);

  const load = async () => {
    setBusy(true); setErr('');
    try {
      const fd = new FormData();
      if (sheetName) fd.append('sheet_name', sheetName);
      fd.append('header_row', String(headerRow));
      await api.post('/data/load-from-staged', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      onLoaded?.();
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Load failed');
    } finally { setBusy(false); }
  };

  const cols = previewRows.length > 0 ? Object.keys(previewRows[0]) : [];
  const maxHeader = Math.max(0, Math.min(50, previewRows.length - 1));

  return (
    <Box sx={{ mt: 2 }}>
      {stagedFile.file_type === 'excel' && (
        <TextField select size="small" label="Select Sheet" value={sheetName}
          onChange={(e) => setSheetName(e.target.value)} sx={{ maxWidth: 360, mb: 2 }}>
          {(stagedFile.sheets || []).map((s) => <MenuItem key={s} value={s}>{s}</MenuItem>)}
        </TextField>
      )}

      {busy && <LinearProgress sx={{ mb: 1 }} />}
      {err && <Alert severity="error" sx={{ mb: 1 }}>{err}</Alert>}

      <Typography variant="subtitle2" sx={{ mb: 1 }}>Preview Data:</Typography>
      <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 320, mb: 2 }}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 600, bgcolor: '#FBFAFC' }}>Row</TableCell>
              {cols.map((c) => (
                <TableCell key={c} sx={{ fontWeight: 600, bgcolor: '#FBFAFC' }}>{c}</TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {previewRows.map((row, i) => (
              <TableRow key={i}
                sx={i === headerRow ? { bgcolor: '#dbeafe' } : (i < headerRow ? { bgcolor: '#fef3c7' } : {})}>
                <TableCell sx={{ fontWeight: 600, color: '#64748b' }}>{i}</TableCell>
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

      <Grid container spacing={1.5} alignItems="center">
        <Grid item xs={12} sm={6}>
          <TextField fullWidth size="small" type="number"
            label="Select header row (0 = first row)"
            value={headerRow}
            onChange={(e) => {
              const v = parseInt(e.target.value || '0', 10);
              setHeaderRow(Math.max(0, Math.min(maxHeader, v)));
            }}
            inputProps={{ min: 0, max: maxHeader }} />
        </Grid>
        <Grid item xs={6} sm={3}>
          <Box sx={{ p: 1.25, border: '1px solid', borderColor: 'divider', borderRadius: 2, textAlign: 'center' }}>
            <Typography variant="caption" color="text.secondary">Header</Typography>
            <Typography variant="h6">Row {headerRow}</Typography>
          </Box>
        </Grid>
        <Grid item xs={6} sm={3}>
          <Button fullWidth variant="contained" onClick={load} disabled={busy}>Load Data</Button>
        </Grid>
      </Grid>

      {headerRow > 0 && (
        <Alert severity="info" sx={{ mt: 1.5 }}>
          Row {headerRow} will be used as column headers. Rows 0-{headerRow - 1} will be skipped.
        </Alert>
      )}
    </Box>
  );
}
