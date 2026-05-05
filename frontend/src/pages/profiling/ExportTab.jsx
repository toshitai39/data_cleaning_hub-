import { useState } from 'react';
import { Box, Stack, Button, Typography, Alert } from '@mui/material';
import DownloadIcon from '@mui/icons-material/Download';
import api from '../../api.js';

export default function ExportTab() {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');

  const downloadBlob = async (path, defaultName) => {
    setBusy(true); setErr(''); setMsg('');
    try {
      const res = await api.post(path, null, { responseType: 'blob' });
      const cd = res.headers['content-disposition'] || '';
      const m = cd.match(/filename="?([^"]+)"?/);
      const filename = m ? m[1] : defaultName;
      const url = URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url; a.download = filename; a.click();
      URL.revokeObjectURL(url);
      setMsg(`${filename} downloaded`);
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Export failed');
    } finally { setBusy(false); }
  };

  return (
    <Box>
      <Typography variant="h6" gutterBottom>Export Profiling Report</Typography>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
        <Button fullWidth variant="contained" startIcon={<DownloadIcon />} disabled={busy}
                onClick={() => downloadBlob('/profile/export/excel', 'profile.xlsx')}>
          Generate Excel Report
        </Button>
        <Button fullWidth variant="contained" startIcon={<DownloadIcon />} disabled={busy}
                onClick={() => downloadBlob('/profile/export/json', 'profile.json')}>
          Generate JSON Report
        </Button>
      </Stack>
      {msg && <Alert severity="success" sx={{ mt: 2 }}>{msg}</Alert>}
      {err && <Alert severity="error" sx={{ mt: 2 }}>{err}</Alert>}
    </Box>
  );
}
