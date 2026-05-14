import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Box, Typography, Paper, Chip, Stack, Alert, LinearProgress, Button,
  TextField, InputAdornment, CircularProgress,
  Table, TableHead, TableBody, TableRow, TableCell, TableContainer, Tooltip,
  Accordion, AccordionSummary, AccordionDetails,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import AutoAwesomeOutlinedIcon from '@mui/icons-material/AutoAwesomeOutlined';
import api from '../../api.js';

const STATUS_TONE = (rate) => {
  if (rate >= 0.99) return { fg: '#0E5226', bg: '#DCFCE7', label: 'Strong' };
  if (rate >= 0.95) return { fg: '#0E5226', bg: '#ECFDF5', label: 'Acceptable' };
  if (rate >= 0.80) return { fg: '#7F5F00', bg: '#FEF3C7', label: 'Watch' };
  if (rate >= 0.50) return { fg: '#7F5F00', bg: '#FFE4B5', label: 'Low' };
  return { fg: '#7F1D1D', bg: '#FBEAEA', label: 'Critical' };
};


function ValidityBar({ valid, invalid, blank, total }) {
  const v = total ? (valid / total) * 100 : 0;
  const i = total ? (invalid / total) * 100 : 0;
  const b = total ? (blank / total) * 100 : 0;
  return (
    <Box sx={{ display: 'flex', height: 8, borderRadius: 1, overflow: 'hidden', minWidth: 160 }}>
      <Box sx={{ width: `${v}%`, bgcolor: '#16a34a' }} />
      <Box sx={{ width: `${i}%`, bgcolor: '#dc2626' }} />
      <Box sx={{ width: `${b}%`, bgcolor: '#cbd5e1' }} />
    </Box>
  );
}


export default function ValidationDetail() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState(null);
  const [regenerating, setRegenerating] = useState(false);
  const [regenErr, setRegenErr] = useState('');

  const fetchValidation = async () => {
    setLoading(true);
    setErr('');
    try {
      const { data } = await api.get('/profile/validation');
      setData(data);
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Failed to compute validation');
    } finally {
      setLoading(false);
    }
  };

  // Self-heal: kick the CDE recommender to (re)classify every column and
  // emit fresh semantic_types, then re-fetch the Validation report. The
  // POST endpoint reuses the same project-level cache the picker uses so
  // descriptions / recommendations on Load Data also refresh.
  const regenerateClassification = async () => {
    setRegenerating(true);
    setRegenErr('');
    try {
      await api.post('/data/columns-of-interest/generate-glossary');
      await fetchValidation();
    } catch (e) {
      setRegenErr(e?.response?.data?.detail || 'AI classification failed');
    } finally {
      setRegenerating(false);
    }
  };

  // Guard so auto-classification fires at most once per mount.
  const autoClassifiedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const { data } = await api.get('/profile/validation');
        if (cancelled) return;
        setData(data);
        // Backend tells us no glossary exists yet → silently trigger the
        // recommender so the AI's PAN / GSTIN / Email / etc. classifications
        // flow into Validation without making the steward click anything.
        if (data.needs_classification && !autoClassifiedRef.current) {
          autoClassifiedRef.current = true;
          await regenerateClassification();
        }
      } catch (e) {
        if (!cancelled) setErr(e?.response?.data?.detail || 'Failed to compute validation');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fields = useMemo(() => {
    const all = data?.fields || [];
    if (!search.trim()) return all;
    const q = search.toLowerCase();
    return all.filter((f) =>
      f.field.toLowerCase().includes(q) ||
      (f.semantic_type_label || '').toLowerCase().includes(q),
    );
  }, [data, search]);

  if (loading) return <LinearProgress />;
  if (err) return <Alert severity="error">{err}</Alert>;
  if (!data) return null;

  const s = data.summary || {};
  const hasFields = (data.fields || []).length > 0;

  if (!hasFields) {
    const skippedCount = (data.skipped || []).length;
    const aiClassifiedTotal = s.ai_classified_total || skippedCount;
    const breakdown = s.semantic_type_breakdown || [];
    const noAI = aiClassifiedTotal === 0;
    return (
      <Paper variant="outlined" sx={{ p: 3, bgcolor: '#FBFAFC' }}>
        <Stack alignItems="center" textAlign="center" spacing={1}>
          <AutoAwesomeOutlinedIcon sx={{ fontSize: 36, color: '#6A28A8' }} />
          <Typography sx={{ fontFamily: "'Montserrat', sans-serif", fontWeight: 700, fontSize: 18 }}>
            {noAI
              ? 'AI column classification not generated for this dataset'
              : 'No format-validatable columns in this dataset'}
          </Typography>
          <Typography sx={{ fontSize: 14, color: '#475569', maxWidth: 720 }}>
            {noAI
              ? 'Open Critical Data Elements on Load Data to generate the AI classification — that runs once per dataset and gets cached.'
              : (
                <>
                  The AI classified all <b>{aiClassifiedTotal}</b> columns, but none have a canonical
                  format with a regulator-defined regex (PAN, GSTIN, TAN, CIN, Email, Indian PIN,
                  ISO-2 country, ISO-3 currency, IFSC, IBAN, SWIFT, etc.). Validation only scores
                  those — every other column is covered by <b>Completeness</b>, <b>Standardisation</b>,
                  or <b>Accuracy</b> instead.
                </>
              )}
          </Typography>
        </Stack>

        {breakdown.length > 0 && (
          <Box sx={{ mt: 2.5 }}>
            <Typography sx={{ fontSize: '0.66rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#8A8A8A', mb: 1 }}>
              What the AI tagged your columns as
            </Typography>
            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
              {breakdown.map((b) => (
                <Chip
                  key={b.semantic_type}
                  size="small"
                  label={`${b.semantic_type} · ${b.count}`}
                  sx={{
                    height: 24,
                    fontSize: '0.74rem',
                    fontWeight: 600,
                    color: '#1A1A1A',
                    bgcolor: '#FFFFFF',
                    border: '1px solid #DDD6E5',
                  }}
                />
              ))}
            </Stack>
            <Typography sx={{ fontSize: 12, color: '#8A8A8A', mt: 1.5 }}>
              If you think a column was mislabelled (e.g. an email column got tagged as <i>free_text_name</i>),
              regenerate. Otherwise this is the correct result for your data — no action needed.
            </Typography>
          </Box>
        )}

        <Box sx={{ textAlign: 'center', mt: 2.5 }}>
          <Button
            variant="outlined"
            size="small"
            startIcon={regenerating ? <CircularProgress size={14} /> : <AutoAwesomeOutlinedIcon sx={{ fontSize: 16 }} />}
            onClick={regenerateClassification}
            disabled={regenerating}
          >
            {regenerating ? 'Reclassifying…' : (noAI ? 'Generate AI classification' : 'Regenerate AI classification')}
          </Button>
          {regenErr && (
            <Alert severity="error" sx={{ mt: 2, textAlign: 'left' }}>{regenErr}</Alert>
          )}
        </Box>
      </Paper>
    );
  }

  return (
    <Box>
      <Paper variant="outlined" sx={{ p: 2, mb: 2, bgcolor: '#FBFAFC' }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={3} alignItems="flex-start" justifyContent="space-between">
          <Stack direction="row" spacing={3} alignItems="flex-start">
            <Box>
              <Typography sx={{ fontSize: '0.66rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#8A8A8A' }}>
                Overall validity rate
              </Typography>
              <Typography sx={{ fontFamily: "'Montserrat', sans-serif", fontWeight: 700, fontSize: 28 }}>
                {((s.overall_validity_rate || 0) * 100).toFixed(1)}%
              </Typography>
            </Box>
            <Box>
              <Typography sx={{ fontSize: '0.66rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#8A8A8A' }}>
                Typed columns
              </Typography>
              <Typography sx={{ fontFamily: "'Montserrat', sans-serif", fontWeight: 700, fontSize: 28 }}>
                {s.typed_columns}
              </Typography>
            </Box>
            <Box>
              <Typography sx={{ fontSize: '0.66rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#7F1D1D' }}>
                Invalid values
              </Typography>
              <Typography sx={{ fontFamily: "'Montserrat', sans-serif", fontWeight: 700, fontSize: 28, color: '#7F1D1D' }}>
                {(s.invalid_values || 0).toLocaleString()}
              </Typography>
            </Box>
            <Box>
              <Typography sx={{ fontSize: '0.66rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#8A8A8A' }}>
                Blank values
              </Typography>
              <Typography sx={{ fontFamily: "'Montserrat', sans-serif", fontWeight: 700, fontSize: 28, color: '#475569' }}>
                {(s.blank_values || 0).toLocaleString()}
              </Typography>
            </Box>
          </Stack>
          <Tooltip title="Re-run the AI to refresh column classifications, then recompute Validation.">
            <Button
              size="small"
              variant="outlined"
              onClick={regenerateClassification}
              disabled={regenerating}
              startIcon={regenerating ? <CircularProgress size={14} /> : <AutoAwesomeOutlinedIcon sx={{ fontSize: 16 }} />}
            >
              {regenerating ? 'Reclassifying…' : 'Regenerate'}
            </Button>
          </Tooltip>
        </Stack>
        {regenErr && (
          <Alert severity="error" sx={{ mt: 1.5 }}>{regenErr}</Alert>
        )}
      </Paper>

      <TextField
        size="small"
        fullWidth
        placeholder="Filter by field name or type (PAN, GSTIN, Email…)"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        InputProps={{
          startAdornment: (
            <InputAdornment position="start">
              <SearchIcon fontSize="small" />
            </InputAdornment>
          ),
        }}
        sx={{ mb: 1.5 }}
      />

      <TableContainer component={Paper} variant="outlined" sx={{ mb: 2 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Field</TableCell>
              <TableCell sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Type</TableCell>
              <TableCell sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em' }} align="right">Valid</TableCell>
              <TableCell sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em' }} align="right">Invalid</TableCell>
              <TableCell sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em' }} align="right">Blank</TableCell>
              <TableCell sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Composition</TableCell>
              <TableCell sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Validity</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {fields.map((f) => {
              const tone = STATUS_TONE(f.validity_rate);
              const rows = s.rows || (f.records_with_value + f.blank);
              return (
                <TableRow key={f.field} hover>
                  <TableCell sx={{ py: 0.85 }}>
                    <Tooltip title={f.format_rule} placement="top-start">
                      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.84rem', fontWeight: 600 }}>{f.field}</Typography>
                    </Tooltip>
                  </TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={f.semantic_type_label}
                      sx={{ height: 20, fontSize: '0.68rem', fontWeight: 700, color: '#6A28A8', bgcolor: '#F4ECF9', border: 'none' }}
                    />
                  </TableCell>
                  <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums', fontSize: '0.82rem', color: '#0E5226' }}>
                    {(f.valid || 0).toLocaleString()}
                  </TableCell>
                  <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums', fontSize: '0.82rem', color: f.invalid > 0 ? '#7F1D1D' : '#8A8A8A', fontWeight: f.invalid > 0 ? 700 : 400 }}>
                    {(f.invalid || 0).toLocaleString()}
                  </TableCell>
                  <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums', fontSize: '0.82rem', color: '#475569' }}>
                    {(f.blank || 0).toLocaleString()}
                  </TableCell>
                  <TableCell sx={{ minWidth: 180 }}>
                    <ValidityBar valid={f.valid} invalid={f.invalid} blank={f.blank} total={rows} />
                  </TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={`${(f.validity_rate * 100).toFixed(1)}%`}
                      sx={{ height: 22, fontSize: '0.7rem', fontWeight: 700, color: tone.fg, bgcolor: tone.bg, border: 'none' }}
                    />
                  </TableCell>
                </TableRow>
              );
            })}
            {fields.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} sx={{ color: '#8A8A8A', textAlign: 'center', py: 3 }}>
                  No fields match your filter.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>

      <Typography sx={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#6A28A8', fontWeight: 700, mb: 1 }}>
        Sample invalid values
      </Typography>
      {fields.filter((f) => (f.samples_invalid || []).length > 0).map((f) => (
        <Accordion
          key={`acc-${f.field}`}
          expanded={expanded === f.field}
          onChange={(_, exp) => setExpanded(exp ? f.field : null)}
          disableGutters
          elevation={0}
          sx={{ border: '1px solid', borderColor: 'divider', '&:before': { display: 'none' }, mb: 0.75 }}
        >
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Stack direction="row" spacing={1.5} alignItems="center" sx={{ width: '100%' }}>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.86rem', fontWeight: 700 }}>{f.field}</Typography>
              <Chip
                size="small"
                label={f.semantic_type_label}
                sx={{ height: 18, fontSize: '0.66rem', fontWeight: 700, color: '#6A28A8', bgcolor: '#F4ECF9', border: 'none' }}
              />
              <Typography sx={{ fontSize: '0.78rem', color: '#7F1D1D', fontWeight: 600 }}>
                {f.invalid.toLocaleString()} invalid · format: {f.format_rule}
              </Typography>
            </Stack>
          </AccordionSummary>
          <AccordionDetails>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A', fontWeight: 700, width: 100 }}>Row #</TableCell>
                    <TableCell sx={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A', fontWeight: 700 }}>Invalid value</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(f.samples_invalid || []).map((s, i) => (
                    <TableRow key={i}>
                      <TableCell sx={{ fontVariantNumeric: 'tabular-nums' }}>{s.row}</TableCell>
                      <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.84rem' }}>{s.value || <span style={{ color: '#CBD5E1' }}>(empty)</span>}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </AccordionDetails>
        </Accordion>
      ))}

      {(data.skipped || []).length > 0 && (
        <Alert severity="info" sx={{ mt: 2 }}>
          {data.skipped.length} column{data.skipped.length === 1 ? '' : 's'} aren't typed — they're free-text or
          enum fields that Validation doesn't score (e.g. {data.skipped.slice(0, 3).map((s) => s.field).join(', ')}
          {data.skipped.length > 3 ? '…' : ''}). Standardisation and Completeness still cover them.
        </Alert>
      )}
    </Box>
  );
}
