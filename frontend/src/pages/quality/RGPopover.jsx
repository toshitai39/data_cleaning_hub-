import { useEffect, useState } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions, Button, Stack,
  Typography, Checkbox, FormControlLabel, Alert,
} from '@mui/material';
import api from '../../api.js';

export default function RGPopover({ open, onClose, column, onAdded }) {
  const [available, setAvailable] = useState(true);
  const [options, setOptions] = useState([]);
  const [picked, setPicked] = useState({});
  const [err, setErr] = useState('');

  useEffect(() => {
    if (!open) return;
    setErr(''); setPicked({});
    api.get(`/quality/rg-rules/${encodeURIComponent(column)}`)
      .then((r) => { setAvailable(r.data.available); setOptions(r.data.options); })
      .catch((e) => setErr(e?.response?.data?.detail || 'Failed'));
  }, [open, column]);

  const toggle = (label) => setPicked((p) => ({ ...p, [label]: !p[label] }));

  const add = async () => {
    const labels = Object.entries(picked).filter(([_, v]) => v).map(([k]) => k);
    if (!labels.length) return;
    try {
      const { data } = await api.post(`/quality/rg-add/${encodeURIComponent(column)}`, { labels });
      onAdded?.(data.added);
      onClose();
    } catch (e) { setErr(e?.response?.data?.detail || 'Failed'); }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{column} — From Rule Generator</DialogTitle>
      <DialogContent>
        {err && <Alert severity="error" sx={{ mb: 1 }}>{err}</Alert>}
        {!available && (
          <Alert severity="info">Generate rules in the <b>Rule Generator</b> tab first.</Alert>
        )}
        {available && options.length === 0 && (
          <Alert severity="info">
            No executable rules for this column (e.g. uniqueness cannot map to regex here).
          </Alert>
        )}
        {available && options.length > 0 && (
          <Stack spacing={0.5}>
            {options.map((o) => (
              <FormControlLabel
                key={o.label}
                control={<Checkbox checked={!!picked[o.label]} onChange={() => toggle(o.label)} />}
                label={<Typography variant="body2">{o.label}</Typography>}
              />
            ))}
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={add}
          disabled={!available || Object.values(picked).every((v) => !v)}>
          Add selected
        </Button>
      </DialogActions>
    </Dialog>
  );
}
