import { useEffect, useMemo, useState } from 'react';
import {
  Box, Paper, Stack, Typography, Button, Chip, LinearProgress, Alert,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  TextField, InputAdornment, IconButton, Tooltip, Dialog, DialogTitle,
  DialogContent, DialogActions,
} from '@mui/material';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import RefreshIcon from '@mui/icons-material/Refresh';
import EditIcon from '@mui/icons-material/Edit';
import SearchIcon from '@mui/icons-material/Search';
import MenuBookOutlinedIcon from '@mui/icons-material/MenuBookOutlined';
import api from '../../api.js';

function semanticChipColor(type) {
  const t = String(type || '').toLowerCase();
  if (t === 'unknown' || !t) return { bgcolor: '#f1f5f9', color: '#475569' };
  if (t.includes('email')) return { bgcolor: '#e0f2fe', color: '#075985' };
  if (t.includes('phone')) return { bgcolor: '#fef3c7', color: '#92400e' };
  if (t.includes('id') || t.includes('identifier')) return { bgcolor: '#ede9fe', color: '#5b21b6' };
  if (t.includes('name')) return { bgcolor: '#dcfce7', color: '#166534' };
  if (t.includes('country') || t.includes('region') || t.includes('state') || t.includes('city') || t.includes('address')) {
    return { bgcolor: '#fce7f3', color: '#9d174d' };
  }
  if (t.includes('date') || t.includes('year') || t.includes('time')) return { bgcolor: '#ccfbf1', color: '#115e59' };
  if (t.includes('currency') || t.includes('amount') || t.includes('percent') || t.includes('ratio') || t.includes('decimal') || t.includes('integer') || t.includes('count') || t.includes('quantity')) {
    return { bgcolor: '#dbeafe', color: '#1e3a8a' };
  }
  if (t.includes('pan') || t.includes('vat') || t.includes('gst') || t.includes('tax')) {
    return { bgcolor: '#fef9c3', color: '#854d0e' };
  }
  return { bgcolor: '#f1f5f9', color: '#334155' };
}

export default function SemanticGlossary() {
  const [entries, setEntries] = useState([]);
  const [generated, setGenerated] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [editTarget, setEditTarget] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [editBusy, setEditBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .get('/profile/semantic-glossary')
      .then(({ data }) => {
        if (cancelled) return;
        setEntries(data.entries || []);
        setGenerated(!!data.generated);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const filtered = useMemo(() => {
    if (!search.trim()) return entries;
    const q = search.toLowerCase();
    return entries.filter((e) =>
      [e.column, e.semantic_type, e.display_name, e.description]
        .some((v) => String(v || '').toLowerCase().includes(q)),
    );
  }, [entries, search]);

  const counts = useMemo(() => {
    const map = new Map();
    for (const e of entries) {
      const t = e.semantic_type || 'unknown';
      map.set(t, (map.get(t) || 0) + 1);
    }
    return Array.from(map.entries()).sort((a, b) => b[1] - a[1]);
  }, [entries]);

  const generate = async () => {
    setBusy(true);
    setError('');
    try {
      const { data } = await api.post('/profile/semantic-glossary/generate');
      setEntries(data.entries || []);
      setGenerated(true);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Glossary generation failed');
    } finally {
      setBusy(false);
    }
  };

  const clear = async () => {
    setBusy(true);
    setError('');
    try {
      await api.post('/profile/semantic-glossary/clear');
      setEntries([]);
      setGenerated(false);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not clear glossary');
    } finally {
      setBusy(false);
    }
  };

  const openEdit = (entry) => {
    setEditTarget(entry);
    setEditForm({
      semantic_type: entry.semantic_type || '',
      display_name: entry.display_name || '',
      description: entry.description || '',
      format_hint: entry.format_hint || '',
    });
  };

  const saveEdit = async () => {
    if (!editTarget) return;
    setEditBusy(true);
    try {
      const { data } = await api.put(
        `/profile/semantic-glossary/${encodeURIComponent(editTarget.column)}`,
        editForm,
      );
      setEntries((prev) => prev.map((e) => (e.column === editTarget.column ? data.entry : e)));
      setEditTarget(null);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Override failed');
    } finally {
      setEditBusy(false);
    }
  };

  return (
    <Paper variant="outlined" sx={{ p: 2.5, mb: 3 }}>
      <Stack
        direction={{ xs: 'column', md: 'row' }}
        justifyContent="space-between"
        alignItems={{ xs: 'flex-start', md: 'center' }}
        spacing={1.5}
        sx={{ mb: 1.5 }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
          <MenuBookOutlinedIcon color="primary" />
          <Typography variant="h6" sx={{ fontWeight: 700 }}>Data Glossary</Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          {!generated ? (
            <Button
              variant="contained"
              startIcon={<AutoAwesomeIcon />}
              onClick={generate}
              disabled={busy}
            >
              {busy ? 'Inferring…' : 'Generate Data Glossary'}
            </Button>
          ) : (
            <>
              <Button
                variant="outlined"
                startIcon={<RefreshIcon />}
                onClick={generate}
                disabled={busy}
              >
                Regenerate
              </Button>
              <Button variant="outlined" color="error" onClick={clear} disabled={busy}>
                Clear
              </Button>
            </>
          )}
        </Stack>
      </Stack>

      {busy && <LinearProgress sx={{ mb: 1.5 }} />}
      {error && <Alert severity="error" sx={{ mb: 1.5 }}>{error}</Alert>}

      {!generated && entries.length === 0 && !busy && (
        <Alert severity="info">Generate the glossary to map each critical data element to a semantic type.</Alert>
      )}

      {generated && entries.length > 0 && (
        <>
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={1.5}
            alignItems={{ xs: 'stretch', sm: 'center' }}
            sx={{ mb: 1.5 }}
          >
            <TextField
              size="small"
              placeholder="Filter columns or types…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon fontSize="small" />
                  </InputAdornment>
                ),
              }}
              sx={{ minWidth: 260, flex: 1 }}
            />
            <Stack direction="row" spacing={0.75} flexWrap="wrap">
              {counts.slice(0, 6).map(([type, n]) => {
                const style = semanticChipColor(type);
                return (
                  <Chip
                    key={type}
                    size="small"
                    label={`${type} × ${n}`}
                    sx={{ bgcolor: style.bgcolor, color: style.color, fontWeight: 600 }}
                  />
                );
              })}
            </Stack>
          </Stack>

          <TableContainer sx={{ maxHeight: 500, border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 700, bgcolor: '#FBFAFC' }}>Critical data element</TableCell>
                  <TableCell sx={{ fontWeight: 700, bgcolor: '#FBFAFC' }}>Semantic Type</TableCell>
                  <TableCell sx={{ fontWeight: 700, bgcolor: '#FBFAFC' }}>Display Name</TableCell>
                  <TableCell sx={{ fontWeight: 700, bgcolor: '#FBFAFC' }}>Description</TableCell>
                  <TableCell sx={{ fontWeight: 700, bgcolor: '#FBFAFC' }}>Format Hint</TableCell>
                  <TableCell sx={{ fontWeight: 700, bgcolor: '#FBFAFC' }}>Confidence</TableCell>
                  <TableCell sx={{ fontWeight: 700, bgcolor: '#FBFAFC', width: 60 }} />
                </TableRow>
              </TableHead>
              <TableBody>
                {filtered.map((entry) => {
                  const style = semanticChipColor(entry.semantic_type);
                  const conf = Math.round(((entry.confidence ?? 0) * 100));
                  return (
                    <TableRow key={entry.column} hover>
                      <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.82rem' }}>
                        {entry.column}
                      </TableCell>
                      <TableCell>
                        <Chip
                          size="small"
                          label={entry.semantic_type || 'unknown'}
                          sx={{ bgcolor: style.bgcolor, color: style.color, fontWeight: 600 }}
                        />
                        {entry.source === 'manual' && (
                          <Chip size="small" label="manual" variant="outlined" sx={{ ml: 0.5 }} />
                        )}
                      </TableCell>
                      <TableCell>{entry.display_name}</TableCell>
                      <TableCell sx={{ fontSize: '0.8rem', maxWidth: 320 }}>
                        <Tooltip title={entry.description || ''}>
                          <span>{entry.description}</span>
                        </Tooltip>
                      </TableCell>
                      <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.75rem', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={entry.format_hint || ''}>
                        {entry.format_hint || '—'}
                      </TableCell>
                      <TableCell>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                          <Box sx={{
                            width: 60, height: 6, borderRadius: 3,
                            bgcolor: '#e2e8f0', overflow: 'hidden',
                          }}>
                            <Box sx={{
                              width: `${conf}%`, height: '100%',
                              bgcolor: conf >= 80 ? '#16a34a' : conf >= 50 ? '#ca8a04' : '#dc2626',
                            }} />
                          </Box>
                          <Typography variant="caption" color="text.secondary">{conf}%</Typography>
                        </Box>
                      </TableCell>
                      <TableCell>
                        <IconButton size="small" onClick={() => openEdit(entry)}>
                          <EditIcon fontSize="small" />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  );
                })}
                {filtered.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7} align="center" sx={{ py: 3, color: 'text.secondary' }}>
                      No entries match the filter.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>

        </>
      )}

      <Dialog open={!!editTarget} onClose={() => setEditTarget(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Override glossary entry — {editTarget?.column}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Semantic type (snake_case)"
              size="small"
              value={editForm.semantic_type || ''}
              onChange={(e) => setEditForm((f) => ({ ...f, semantic_type: e.target.value }))}
              fullWidth
            />
            <TextField
              label="Display name"
              size="small"
              value={editForm.display_name || ''}
              onChange={(e) => setEditForm((f) => ({ ...f, display_name: e.target.value }))}
              fullWidth
            />
            <TextField
              label="Description"
              size="small"
              value={editForm.description || ''}
              onChange={(e) => setEditForm((f) => ({ ...f, description: e.target.value }))}
              fullWidth
              multiline
              minRows={2}
            />
            <TextField
              label="Format hint (regex or short description)"
              size="small"
              value={editForm.format_hint || ''}
              onChange={(e) => setEditForm((f) => ({ ...f, format_hint: e.target.value }))}
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditTarget(null)} disabled={editBusy}>Cancel</Button>
          <Button variant="contained" onClick={saveEdit} disabled={editBusy}>
            {editBusy ? 'Saving…' : 'Save override'}
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
}
