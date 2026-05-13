import { useState } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions, Button, Stack,
  TextField, MenuItem, Alert, Typography, Box,
} from '@mui/material';
import api from '../../api.js';

export default function AiRegexDialog({ open, onClose, columns }) {
  const [col, setCol] = useState(columns?.[0] || '');
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [sug, setSug] = useState(null);

  const generate = async () => {
    if (!col || !q.trim()) return;
    setBusy(true); setErr(''); setSug(null);
    try {
      const { data } = await api.post('/quality/ai-suggest', { column: col, question: q });
      setSug(data.suggestion);
    } catch (e) { setErr(e?.response?.data?.detail || 'Suggestion failed'); }
    finally { setBusy(false); }
  };

  const close = () => { onClose(); setSug(null); setErr(''); setQ(''); };

  return (
    <Dialog open={open} onClose={close} fullWidth maxWidth="sm">
      <DialogTitle>AI Regex Generator</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 0.5 }}>
          <TextField select label="Critical data element" value={col} onChange={(e) => setCol(e.target.value)} fullWidth>
            {(columns || []).map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
          </TextField>
          <TextField
            label="What to do?"
            multiline minRows={3}
            value={q} onChange={(e) => setQ(e.target.value)}
            placeholder={'Remove special chars\nReplace _ with space\nExtract numbers'}
            fullWidth
          />
          <Button variant="contained" onClick={generate} disabled={busy || !col || !q.trim()}>
            {busy ? 'Generating…' : 'Generate'}
          </Button>
          {err && <Alert severity="error">{err}</Alert>}
          {sug && (
            <Alert severity="success">
              <Typography variant="body2"><b>Generated</b></Typography>
              <Typography variant="caption" sx={{ display: 'block', mt: 0.5 }}>
                {sug.explanation}
              </Typography>
              {sug.pattern && (
                <Box sx={{ mt: 1 }}>
                  <Typography variant="caption">Pattern:</Typography>
                  <TextField value={sug.pattern} fullWidth size="small" InputProps={{ readOnly: true }}
                    sx={{ '& input': { fontFamily: 'monospace' } }} />
                </Box>
              )}
              {sug.replace && (
                <Box sx={{ mt: 1 }}>
                  <Typography variant="caption">Replace:</Typography>
                  <TextField value={sug.replace} fullWidth size="small" InputProps={{ readOnly: true }} />
                </Box>
              )}
              {sug.mode === 'Case' && (
                <Typography variant="caption" sx={{ display: 'block', mt: 1 }}>
                  Case: <b>{sug.case}</b>
                </Typography>
              )}
              <Typography variant="caption" sx={{ display: 'block', mt: 1 }}>
                Mode: <b>{sug.mode}</b>
              </Typography>
            </Alert>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
