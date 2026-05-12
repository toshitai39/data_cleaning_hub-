import { useEffect, useMemo, useState } from 'react';
import {
  Box, Typography, TextField, InputAdornment, Chip,
  Checkbox, FormControlLabel, Button, Stack, Divider, Alert, Tooltip,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import TuneOutlinedIcon from '@mui/icons-material/TuneOutlined';
import api from '../../api.js';
import ContentCard from '../../components/ContentCard.jsx';

export default function ColumnsOfInterest({ onSaved }) {
  const [allCols, setAllCols] = useState([]);
  const [selected, setSelected] = useState([]);
  const [initialSelected, setInitialSelected] = useState([]);
  const [explicit, setExplicit] = useState(false);
  const [search, setSearch] = useState('');
  const [busy, setBusy] = useState(false);
  const [savedAt, setSavedAt] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    api
      .get('/data/columns-of-interest')
      .then(({ data }) => {
        if (cancelled) return;
        setAllCols(data.all || []);
        setSelected(data.selected || []);
        setInitialSelected(data.selected || []);
        setExplicit(!!data.explicit);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const filtered = useMemo(() => {
    if (!search.trim()) return allCols;
    const q = search.toLowerCase();
    return allCols.filter((c) => c.toLowerCase().includes(q));
  }, [allCols, search]);

  const selectedSet = useMemo(() => new Set(selected), [selected]);
  const isDirty = useMemo(() => {
    if (selected.length !== initialSelected.length) return true;
    const initSet = new Set(initialSelected);
    return selected.some((c) => !initSet.has(c));
  }, [selected, initialSelected]);

  const toggle = (col) => {
    setSelected((prev) =>
      prev.includes(col) ? prev.filter((c) => c !== col) : [...prev, col],
    );
  };

  const selectAll = () => setSelected([...allCols]);
  const clearAll = () => setSelected([]);
  const invert = () => setSelected(allCols.filter((c) => !selectedSet.has(c)));
  const selectVisible = () => {
    const visibleSet = new Set(filtered);
    setSelected((prev) => Array.from(new Set([...prev, ...filtered])));
    // keep prev selections not in visibleSet untouched
    void visibleSet;
  };

  const save = async () => {
    setBusy(true);
    setError('');
    try {
      const { data } = await api.post('/data/columns-of-interest', { selected });
      setSelected(data.selected || []);
      setInitialSelected(data.selected || []);
      setExplicit(true);
      setSavedAt(new Date());
      if (onSaved) onSaved(data);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not save selection');
    } finally {
      setBusy(false);
    }
  };

  if (allCols.length === 0) return null;

  return (
    <ContentCard sx={{ mb: 2.5, p: 2.5 }}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        alignItems={{ xs: 'flex-start', sm: 'center' }}
        justifyContent="space-between"
        spacing={1.5}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <TuneOutlinedIcon sx={{ fontSize: 20, color: '#6A28A8' }} />
          <Typography
            sx={{
              fontFamily: "'Montserrat', sans-serif",
              fontSize: 16,
              fontWeight: 700,
              color: '#1A1A1A',
            }}
          >
            Columns of interest
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} alignItems="center">
          <Chip
            size="small"
            color={selected.length === allCols.length ? 'default' : 'primary'}
            label={`${selected.length} / ${allCols.length} selected`}
          />
          {!explicit && (
            <Tooltip title="No selection saved yet — all columns are in scope by default">
              <Chip size="small" variant="outlined" label="default: all" />
            </Tooltip>
          )}
        </Stack>
      </Stack>

      <Divider sx={{ my: 1.5 }} />

      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1.5}
        alignItems={{ xs: 'stretch', sm: 'center' }}
        sx={{ mb: 1.5 }}
      >
        <TextField
          size="small"
          placeholder="Filter columns…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          }}
          sx={{ minWidth: 240, flex: 1 }}
        />
        <Stack direction="row" spacing={1}>
          <Button size="small" variant="outlined" onClick={selectAll}>Select all</Button>
          <Button size="small" variant="outlined" onClick={clearAll}>Clear</Button>
          <Button size="small" variant="outlined" onClick={invert}>Invert</Button>
          {search && (
            <Button size="small" variant="outlined" onClick={selectVisible}>
              Add visible
            </Button>
          )}
        </Stack>
      </Stack>

      <Box
        sx={{
          maxHeight: 260,
          overflowY: 'auto',
          border: '1px solid #E7E6E6',
          borderRadius: 1.5,
          bgcolor: '#FBFAFC',
          p: 1.25,
          display: 'grid',
          gridTemplateColumns: {
            xs: '1fr',
            sm: '1fr 1fr',
            md: '1fr 1fr 1fr',
          },
          rowGap: 0.25,
          columnGap: 1,
        }}
      >
        {filtered.length === 0 && (
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ p: 2, gridColumn: '1 / -1', textAlign: 'center' }}
          >
            No columns match your filter.
          </Typography>
        )}
        {filtered.map((col) => (
          <FormControlLabel
            key={col}
            control={
              <Checkbox
                size="small"
                checked={selectedSet.has(col)}
                onChange={() => toggle(col)}
              />
            }
            label={
              <Typography
                variant="body2"
                sx={{
                  fontFamily: 'monospace',
                  fontSize: '0.82rem',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  maxWidth: 220,
                }}
                title={col}
              >
                {col}
              </Typography>
            }
            sx={{ mx: 0 }}
          />
        ))}
      </Box>

      {error && <Alert severity="error" sx={{ mt: 1.5 }}>{error}</Alert>}

      <Stack
        direction="row"
        justifyContent="space-between"
        alignItems="center"
        sx={{ mt: 1.5, flexWrap: 'wrap', gap: 1 }}
      >
        <Typography variant="caption" color="text.secondary">
          {savedAt
            ? `Saved at ${savedAt.toLocaleTimeString()}`
            : isDirty
              ? 'Unsaved changes'
              : explicit
                ? 'Selection saved'
                : 'No changes yet'}
        </Typography>
        <Button
          variant="contained"
          size="small"
          disabled={!isDirty || busy}
          onClick={save}
        >
          {busy ? 'Saving…' : 'Save selection'}
        </Button>
      </Stack>
    </ContentCard>
  );
}
