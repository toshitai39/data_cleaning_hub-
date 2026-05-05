import { useEffect, useState } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions, Button, Stack,
  TextField, MenuItem, Alert,
} from '@mui/material';
import api from '../../api.js';

export function LibrarySaveDialog({ open, onClose, onDone }) {
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const save = async () => {
    if (!name.trim()) return;
    setBusy(true); setErr('');
    try {
      await api.post('/quality/library/save', { name, description: desc });
      onDone?.(name);
      setName(''); setDesc('');
      onClose();
    } catch (e) { setErr(e?.response?.data?.detail || 'Failed'); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>Save to Library</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 0.5 }}>
          <TextField label="Rule set name" value={name} onChange={(e) => setName(e.target.value)} fullWidth />
          <TextField label="Description (optional)" value={desc} onChange={(e) => setDesc(e.target.value)} fullWidth />
          {err && <Alert severity="error">{err}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={save} disabled={busy || !name.trim()}>Save</Button>
      </DialogActions>
    </Dialog>
  );
}

export function LibraryLoadDialog({ open, onClose, onDone }) {
  const [list, setList] = useState([]);
  const [pick, setPick] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  useEffect(() => {
    if (!open) return;
    api.get('/quality/library').then((r) => {
      setList(r.data || []);
      setPick(r.data?.[0]?.name || '');
    });
  }, [open]);

  const load = async () => {
    if (!pick) return;
    setBusy(true); setErr('');
    try {
      const { data } = await api.post('/quality/library/load', { name: pick });
      onDone?.(pick, data.imported);
      onClose();
    } catch (e) { setErr(e?.response?.data?.detail || 'Failed'); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>Load from Library</DialogTitle>
      <DialogContent>
        {list.length === 0 ? (
          <Alert severity="info">No saved rule sets yet.</Alert>
        ) : (
          <Stack spacing={2} sx={{ mt: 0.5 }}>
            <TextField select label="Rule set" value={pick} onChange={(e) => setPick(e.target.value)} fullWidth>
              {list.map((s) => <MenuItem key={s.name} value={s.name}>{s.name}</MenuItem>)}
            </TextField>
            {err && <Alert severity="error">{err}</Alert>}
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={load} disabled={busy || !pick}>Load</Button>
      </DialogActions>
    </Dialog>
  );
}

export function LibraryDeleteDialog({ open, onClose, onDone }) {
  const [list, setList] = useState([]);
  const [pick, setPick] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  useEffect(() => {
    if (!open) return;
    api.get('/quality/library').then((r) => {
      setList(r.data || []);
      setPick(r.data?.[0]?.name || '');
    });
  }, [open]);

  const remove = async () => {
    if (!pick) return;
    setBusy(true); setErr('');
    try {
      await api.delete(`/quality/library/${encodeURIComponent(pick)}`);
      onDone?.(pick);
      onClose();
    } catch (e) { setErr(e?.response?.data?.detail || 'Failed'); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>Delete from Library</DialogTitle>
      <DialogContent>
        {list.length === 0 ? (
          <Alert severity="info">No saved rule sets.</Alert>
        ) : (
          <Stack spacing={2} sx={{ mt: 0.5 }}>
            <TextField select label="Rule set" value={pick} onChange={(e) => setPick(e.target.value)} fullWidth>
              {list.map((s) => <MenuItem key={s.name} value={s.name}>{s.name}</MenuItem>)}
            </TextField>
            {err && <Alert severity="error">{err}</Alert>}
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" color="error" onClick={remove} disabled={busy || !pick}>Delete</Button>
      </DialogActions>
    </Dialog>
  );
}
