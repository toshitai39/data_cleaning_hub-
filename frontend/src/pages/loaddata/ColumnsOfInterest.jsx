import { useEffect, useMemo, useState } from 'react';
import {
  Box, Typography, TextField, InputAdornment, Chip,
  Checkbox, Button, Stack, Divider, Alert, Tooltip, Switch, FormControlLabel,
  CircularProgress,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import TuneOutlinedIcon from '@mui/icons-material/TuneOutlined';
import StarOutlineRoundedIcon from '@mui/icons-material/StarOutlineRounded';
import AutoAwesomeOutlinedIcon from '@mui/icons-material/AutoAwesomeOutlined';
import api from '../../api.js';
import ContentCard from '../../components/ContentCard.jsx';

export default function ColumnsOfInterest({ onSaved }) {
  const [allCols, setAllCols] = useState([]);
  const [meta, setMeta] = useState({});
  const [schema, setSchema] = useState(null);
  const [selected, setSelected] = useState([]);
  const [initialSelected, setInitialSelected] = useState([]);
  const [explicit, setExplicit] = useState(false);
  const [search, setSearch] = useState('');
  const [recommendedOnly, setRecommendedOnly] = useState(false);
  const [hideMissing, setHideMissing] = useState(true);
  const [busy, setBusy] = useState(false);
  const [savedAt, setSavedAt] = useState(null);
  const [error, setError] = useState('');
  // 'unknown' before first GET; then 'ready' (cached), 'missing' (needs LLM),
  // 'generating' (LLM call in flight), 'error' (LLM call failed).
  const [glossaryStatus, setGlossaryStatus] = useState('unknown');
  const [glossaryError, setGlossaryError] = useState('');

  // Trigger the LLM run when the backend says no cached glossary exists.
  // Wrapped in a state-machine guard so we don't auto-retry on failure —
  // the user can hit "Regenerate" manually if they want to retry.
  const generateGlossary = async ({ keepSelection = true } = {}) => {
    setGlossaryStatus('generating');
    setGlossaryError('');
    try {
      const { data } = await api.post('/data/columns-of-interest/generate-glossary');
      if (data.meta) setMeta(data.meta);
      // Backend may return status 'ready' (real AI run) OR 'fallback' (Azure
      // creds missing — we kept the call green but flagged a warning). Both
      // unblock the picker; only 'ready' should swap the default selection.
      const status = data.glossary_status || 'ready';
      setGlossaryStatus(status);
      if (data.warning) setGlossaryError(data.warning);
      if (!keepSelection && !explicit && status === 'ready') {
        const recommended = (data.meta && Object.entries(data.meta)
          .filter(([, m]) => m.recommended && m.in_data !== false)
          .map(([c]) => c)) || [];
        if (recommended.length > 0) {
          setSelected(recommended);
          setInitialSelected(recommended);
        }
      }
    } catch (e) {
      setGlossaryStatus('error');
      setGlossaryError(e?.response?.data?.detail || 'AI description generation failed');
    }
  };

  useEffect(() => {
    let cancelled = false;
    api
      .get('/data/columns-of-interest')
      .then(({ data }) => {
        if (cancelled) return;
        setAllCols(data.all || []);
        setMeta(data.meta || {});
        setSchema(data.schema || null);
        setSelected(data.selected || []);
        setInitialSelected(data.selected || []);
        setExplicit(!!data.explicit);
        const status = data.glossary_status || 'unknown';
        setGlossaryStatus(status);
        if (status === 'missing' && !cancelled) {
          // Auto-trigger generation. Pass keepSelection=false so the first-time
          // experience defaults to the AI-recommended set once it lands.
          generateGlossary({ keepSelection: false });
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const recommendedCols = useMemo(
    () => allCols.filter((c) => meta[c]?.recommended && meta[c]?.in_data !== false),
    [allCols, meta],
  );

  const missingCount = useMemo(
    () => allCols.filter((c) => meta[c]?.in_data === false).length,
    [allCols, meta],
  );

  const filtered = useMemo(() => {
    let base = allCols;
    if (hideMissing) base = base.filter((c) => meta[c]?.in_data !== false);
    if (recommendedOnly) base = base.filter((c) => meta[c]?.recommended);
    if (!search.trim()) return base;
    const q = search.toLowerCase();
    return base.filter((c) => {
      if (c.toLowerCase().includes(q)) return true;
      const desc = meta[c]?.description || '';
      return desc.toLowerCase().includes(q);
    });
  }, [allCols, meta, search, recommendedOnly, hideMissing]);

  const selectedSet = useMemo(() => new Set(selected), [selected]);
  const isDirty = useMemo(() => {
    if (selected.length !== initialSelected.length) return true;
    const initSet = new Set(initialSelected);
    return selected.some((c) => !initSet.has(c));
  }, [selected, initialSelected]);

  // Canonical fields that aren't in the actual extract can't be selected —
  // gate the toggle so a stray click on a disabled row stays a no-op.
  const isSelectable = (col) => meta[col]?.in_data !== false;
  const inDataCols = useMemo(() => allCols.filter(isSelectable), [allCols, meta]);

  const toggle = (col) => {
    if (!isSelectable(col)) return;
    setSelected((prev) =>
      prev.includes(col) ? prev.filter((c) => c !== col) : [...prev, col],
    );
  };

  const selectAll = () => setSelected([...inDataCols]);
  const clearAll = () => setSelected([]);
  const invert = () => setSelected(inDataCols.filter((c) => !selectedSet.has(c)));
  const selectVisible = () => {
    setSelected((prev) => Array.from(new Set([...prev, ...filtered.filter(isSelectable)])));
  };
  // Replace the current selection with the AI's recommended set — one click
  // always lands you on "exactly the recommended fields" regardless of what
  // was previously ticked. Merging-on-top felt broken because a second click
  // produced no visible change once the recommendations were already in.
  const selectRecommended = () => {
    setSelected([...recommendedCols]);
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
            Critical data elements
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} alignItems="center">
          <Chip
            size="small"
            color={selected.length === inDataCols.length ? 'default' : 'primary'}
            label={`${selected.length} / ${inDataCols.length} selected`}
          />
          {!explicit && glossaryStatus === 'ready' && (
            <Tooltip title="AI-recommended fields are pre-selected — uncheck what you don't want.">
              <Chip size="small" variant="outlined" label="AI-suggested default" />
            </Tooltip>
          )}
          {glossaryStatus === 'ready' && (
            <Tooltip title="Re-run the AI to refresh descriptions and recommendations for this dataset.">
              <Button
                size="small"
                variant="text"
                onClick={() => generateGlossary({ keepSelection: true })}
                startIcon={<AutoAwesomeOutlinedIcon sx={{ fontSize: 16 }} />}
                sx={{ minWidth: 0, px: 1 }}
              >
                Regenerate
              </Button>
            </Tooltip>
          )}
        </Stack>
      </Stack>

      {glossaryStatus === 'generating' && (
        <Alert
          severity="info"
          variant="outlined"
          icon={<CircularProgress size={16} />}
          sx={{ mt: 1.5 }}
        >
          <Typography sx={{ fontSize: 13, fontWeight: 600 }}>
            Asking the AI to describe each critical data element and flag the ones
            worth focusing on…
          </Typography>
          <Typography sx={{ fontSize: 12, color: '#475569', mt: 0.25 }}>
            Usually 5–15 seconds. The result is cached for this dataset.
          </Typography>
        </Alert>
      )}
      {glossaryStatus === 'error' && (
        <Alert
          severity="warning"
          variant="outlined"
          sx={{ mt: 1.5 }}
          action={
            <Button
              size="small"
              variant="outlined"
              onClick={() => generateGlossary({ keepSelection: true })}
            >
              Retry
            </Button>
          }
        >
          <Typography sx={{ fontSize: 13, fontWeight: 600 }}>
            Couldn't generate AI descriptions — {glossaryError || 'unknown error'}.
          </Typography>
          <Typography sx={{ fontSize: 12, color: '#475569', mt: 0.25 }}>
            You can still pick critical data elements manually; rows show dtype + sample values as a fallback.
          </Typography>
        </Alert>
      )}
      {glossaryStatus === 'fallback' && glossaryError && (
        <Alert severity="info" variant="outlined" sx={{ mt: 1.5 }}>
          <Typography sx={{ fontSize: 13, fontWeight: 600 }}>
            AI descriptions are off — {glossaryError}
          </Typography>
        </Alert>
      )}

      {schema?.is_canonical && (
        <Alert
          severity="info"
          variant="outlined"
          sx={{ mt: 1.5, '& .MuiAlert-message': { width: '100%' } }}
        >
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            justifyContent="space-between"
            alignItems={{ xs: 'flex-start', sm: 'center' }}
            spacing={1}
          >
            <Box>
              <Typography sx={{ fontSize: 13, fontWeight: 700 }}>
                Canonical {schema.stream_label || 'stream'} schema · {schema.system_label}
              </Typography>
              <Typography sx={{ fontSize: 12, color: '#475569', mt: 0.25 }}>
                Showing the full standard field set. Greyed-out fields aren't in your
                current extract and can't be selected — upload the missing tables to enable them.
              </Typography>
            </Box>
            {missingCount > 0 && (
              <FormControlLabel
                control={
                  <Switch
                    size="small"
                    checked={hideMissing}
                    onChange={(e) => setHideMissing(e.target.checked)}
                  />
                }
                label={
                  <Typography variant="caption" sx={{ fontWeight: 600 }}>
                    Hide missing ({missingCount})
                  </Typography>
                }
                sx={{ mx: 0 }}
              />
            )}
          </Stack>
        </Alert>
      )}

      <Divider sx={{ my: 1.5 }} />

      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1.5}
        alignItems={{ xs: 'stretch', sm: 'center' }}
        sx={{ mb: 1.5 }}
      >
        <TextField
          size="small"
          placeholder="Filter critical data elements or their description…"
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
        {recommendedCols.length > 0 && (
          <FormControlLabel
            control={
              <Switch
                size="small"
                checked={recommendedOnly}
                onChange={(e) => setRecommendedOnly(e.target.checked)}
              />
            }
            label={
              <Typography variant="caption" sx={{ fontWeight: 600 }}>
                Recommended only ({recommendedCols.length})
              </Typography>
            }
            sx={{ mx: 0 }}
          />
        )}
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          {recommendedCols.length > 0 && (
            <Button
              size="small"
              variant="outlined"
              onClick={selectRecommended}
              startIcon={<StarOutlineRoundedIcon sx={{ fontSize: 16 }} />}
            >
              Select recommended
            </Button>
          )}
          <Button size="small" variant="outlined" onClick={selectAll}>Select all</Button>
          <Button size="small" variant="outlined" onClick={clearAll}>Clear</Button>
          <Button size="small" variant="outlined" onClick={invert}>Invert</Button>
          {(search || recommendedOnly) && (
            <Button size="small" variant="outlined" onClick={selectVisible}>
              Add visible
            </Button>
          )}
        </Stack>
      </Stack>

      <Box
        sx={{
          maxHeight: 360,
          overflowY: 'auto',
          border: '1px solid #E7E6E6',
          borderRadius: 1.5,
          bgcolor: '#FBFAFC',
          p: 0.5,
        }}
      >
        {filtered.length === 0 && (
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ p: 2, textAlign: 'center' }}
          >
            No critical data elements match your filter.
          </Typography>
        )}
        {filtered.map((col) => {
          const m = meta[col] || {};
          const isChecked = selectedSet.has(col);
          const missing = m.in_data === false;
          const isPending = m.source === 'pending';
          const isFallback = m.source === 'fallback';
          return (
            <Box
              key={col}
              onClick={() => toggle(col)}
              sx={{
                display: 'grid',
                gridTemplateColumns: 'auto 1fr auto',
                alignItems: 'flex-start',
                gap: 1,
                px: 1,
                py: 0.85,
                borderRadius: 1,
                cursor: missing ? 'not-allowed' : 'pointer',
                opacity: missing ? 0.55 : 1,
                bgcolor: isChecked ? '#F4ECF9' : 'transparent',
                '&:hover': missing
                  ? { bgcolor: 'transparent' }
                  : { bgcolor: isChecked ? '#EADDF4' : '#F1ECF6' },
                '& + &': { borderTop: '1px solid #ECEAF1' },
              }}
            >
              <Checkbox
                size="small"
                checked={isChecked}
                disabled={missing}
                onChange={() => toggle(col)}
                onClick={(e) => e.stopPropagation()}
                sx={{ p: 0.5, mt: '-2px' }}
              />
              <Box sx={{ minWidth: 0 }}>
                <Stack direction="row" spacing={0.75} alignItems="center" sx={{ flexWrap: 'wrap' }}>
                  <Tooltip title={col} placement="top-start">
                    <Typography
                      sx={{
                        fontFamily: 'monospace',
                        fontSize: '0.86rem',
                        fontWeight: 600,
                        color: '#1A1A1A',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        maxWidth: 240,
                      }}
                    >
                      {col}
                    </Typography>
                  </Tooltip>
                  {isFallback && (
                    <Tooltip title="AI couldn't classify this field — falling back to dtype + sample preview.">
                      <Chip
                        size="small"
                        label="dtype"
                        sx={{
                          height: 18,
                          fontSize: '0.66rem',
                          fontWeight: 700,
                          color: '#475569',
                          bgcolor: '#F1F5F9',
                          border: 'none',
                          '& .MuiChip-label': { px: 0.75 },
                        }}
                      />
                    </Tooltip>
                  )}
                  {missing && (
                    <Tooltip title="This field belongs to the canonical schema but isn't present in your current extract. Upload the missing source table to enable it.">
                      <Chip
                        size="small"
                        label="Not in data"
                        sx={{
                          height: 18,
                          fontSize: '0.66rem',
                          fontWeight: 700,
                          color: '#7F1D1D',
                          bgcolor: '#FBEAEA',
                          border: 'none',
                          '& .MuiChip-label': { px: 0.75 },
                        }}
                      />
                    </Tooltip>
                  )}
                </Stack>
                {isPending ? (
                  <Typography
                    sx={{
                      fontSize: '0.76rem',
                      color: '#A096C2',
                      fontStyle: 'italic',
                      mt: 0.25,
                    }}
                  >
                    Description pending — AI is analyzing this field…
                  </Typography>
                ) : m.description ? (
                  <Tooltip
                    title={m.reason ? `${m.description}\n\nWhy: ${m.reason}` : m.description}
                    placement="bottom-start"
                  >
                    <Typography
                      sx={{
                        fontSize: '0.76rem',
                        color: isFallback ? '#A096C2' : '#555555',
                        fontStyle: isFallback ? 'italic' : 'normal',
                        mt: 0.25,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        display: '-webkit-box',
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: 'vertical',
                      }}
                    >
                      {m.description}
                    </Typography>
                  </Tooltip>
                ) : null}
              </Box>
              {m.recommended && (
                <Tooltip title={m.reason || 'AI flagged this field as a critical data element.'}>
                  <Chip
                    size="small"
                    icon={<StarOutlineRoundedIcon sx={{ fontSize: 14, color: '#6A28A8 !important' }} />}
                    label="Recommended"
                    sx={{
                      height: 22,
                      fontSize: '0.68rem',
                      fontWeight: 700,
                      color: '#6A28A8',
                      bgcolor: '#F4ECF9',
                      border: '1px solid #EADDF4',
                      '& .MuiChip-label': { px: 0.75 },
                    }}
                  />
                </Tooltip>
              )}
            </Box>
          );
        })}
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
          disabled={busy}
          onClick={save}
          sx={{
            // Default MUI disabled state turns the purple gradient into
            // dark-grey-on-dark — unreadable. Force a high-contrast disabled
            // treatment instead.
            '&.Mui-disabled': {
              background: '#E7E6E6',
              color: '#8A8A8A',
              boxShadow: 'none',
            },
          }}
        >
          {busy ? 'Saving…' : 'Save selection'}
        </Button>
      </Stack>
    </ContentCard>
  );
}
