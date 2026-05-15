import { useEffect, useMemo, useState } from 'react';
import {
  Box, Typography, Grid, Paper, Chip, Stack, Alert, LinearProgress,
  TextField, InputAdornment, Switch, FormControlLabel,
  Table, TableHead, TableBody, TableRow, TableCell, TableContainer, Tooltip,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import StarOutlineRoundedIcon from '@mui/icons-material/StarOutlineRounded';
import api from '../../api.js';
import { useDataset } from '../../context/DatasetContext.jsx';

const STATUS_STYLE = {
  Complete:    { fg: '#0E5226', bg: '#DCFCE7' },
  Acceptable:  { fg: '#0E5226', bg: '#ECFDF5' },
  Watch:       { fg: '#7F5F00', bg: '#FEF3C7' },
  Low:         { fg: '#7F5F00', bg: '#FFE4B5' },
  Critical:    { fg: '#7F1D1D', bg: '#FBEAEA' },
  Empty:       { fg: '#475569', bg: '#F1F5F9' },
};

const BUCKET_TONE = [
  { match: /^Complete/,    fg: '#0E5226', bg: '#DCFCE7' },
  { match: /^Acceptable/,  fg: '#0E5226', bg: '#ECFDF5' },
  { match: /^Low/,         fg: '#7F5F00', bg: '#FEF3C7' },
  { match: /^Critical/,    fg: '#7F1D1D', bg: '#FBEAEA' },
  { match: /^Empty/,       fg: '#475569', bg: '#F1F5F9' },
];


function BucketCard({ label, count }) {
  const tone = BUCKET_TONE.find((t) => t.match.test(label)) || BUCKET_TONE[4];
  return (
    <Paper
      variant="outlined"
      sx={{
        p: 1.75,
        bgcolor: '#FFFFFF',
        borderColor: tone.bg,
        height: '100%',
      }}
    >
      <Typography
        sx={{
          fontSize: '0.66rem',
          fontWeight: 700,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          color: tone.fg,
          mb: 0.5,
        }}
      >
        {label}
      </Typography>
      <Typography
        sx={{
          fontFamily: "'Montserrat', sans-serif",
          fontWeight: 700,
          fontSize: 28,
          lineHeight: 1,
          color: '#1A1A1A',
        }}
      >
        {count}
      </Typography>
    </Paper>
  );
}


function FillBar({ pct, status }) {
  const tone = STATUS_STYLE[status] || STATUS_STYLE.Acceptable;
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 130 }}>
      <Box sx={{ flex: 1, height: 6, bgcolor: '#F1F5F9', borderRadius: 1, overflow: 'hidden' }}>
        <Box sx={{ width: `${Math.round(pct * 100)}%`, height: '100%', bgcolor: tone.fg, opacity: 0.85 }} />
      </Box>
      <Typography sx={{ fontSize: '0.78rem', fontWeight: 700, fontVariantNumeric: 'tabular-nums', minWidth: 36, textAlign: 'right' }}>
        {(pct * 100).toFixed(1)}%
      </Typography>
    </Box>
  );
}


export default function CompletenessTab() {
  const { state } = useDataset();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [search, setSearch] = useState('');
  const [cdeOnly, setCdeOnly] = useState(false);
  const [issuesOnly, setIssuesOnly] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    // source=current → reflects post-cleansing state. The dep on
    // state.operations re-fires this effect every time Cleansing /
    // Find Duplicates / Reset mutates the working df, so the drill-
    // down never lags behind the top scorecard.
    api
      .get('/profile/completeness', { params: { source: 'current' } })
      .then(({ data }) => { if (!cancelled) setData(data); })
      .catch((e) => { if (!cancelled) setErr(e?.response?.data?.detail || 'Failed to compute completeness'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [state.operations]);

  const fields = useMemo(() => {
    const all = data?.fields || [];
    let base = all;
    if (cdeOnly) base = base.filter((f) => f.is_cde);
    if (issuesOnly) base = base.filter((f) => f.status !== 'Complete');
    if (search.trim()) {
      const q = search.toLowerCase();
      base = base.filter((f) =>
        f.field.toLowerCase().includes(q) ||
        (f.semantic_type || '').toLowerCase().includes(q),
      );
    }
    return base;
  }, [data, search, cdeOnly, issuesOnly]);

  if (loading) return <LinearProgress />;
  if (err) return <Alert severity="error">{err}</Alert>;
  if (!data) return null;

  const s = data.summary || {};
  const ctx = data.project_context || {};

  return (
    <Box>
      {/* Headline strip: overall fill, CDE fill, stream context */}
      <Paper variant="outlined" sx={{ p: 2, mb: 2, bgcolor: '#FBFAFC' }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={3} alignItems="flex-start" justifyContent="space-between">
          <Stack direction="row" spacing={3}>
            <Box>
              <Typography sx={{ fontSize: '0.66rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#8A8A8A' }}>
                Overall fill rate
              </Typography>
              <Typography sx={{ fontFamily: "'Montserrat', sans-serif", fontWeight: 700, fontSize: 28 }}>
                {((s.overall_fill_rate || 0) * 100).toFixed(1)}%
              </Typography>
            </Box>
            {s.cde_fill_rate != null && (
              <Box>
                <Typography sx={{ fontSize: '0.66rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#6A28A8' }}>
                  CDE fill rate · {s.cde_count} fields
                </Typography>
                <Typography sx={{ fontFamily: "'Montserrat', sans-serif", fontWeight: 700, fontSize: 28, color: '#6A28A8' }}>
                  {(s.cde_fill_rate * 100).toFixed(1)}%
                </Typography>
              </Box>
            )}
            <Box>
              <Typography sx={{ fontSize: '0.66rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#8A8A8A' }}>
                Scope
              </Typography>
              <Typography sx={{ fontSize: 14, fontWeight: 600, color: '#1A1A1A' }}>
                {(s.rows || 0).toLocaleString()} rows · {s.total_fields} fields
              </Typography>
            </Box>
          </Stack>
          {ctx.stream_label && (
            <Tooltip title={`Master-data context informs Uniqueness scoring + rule generation for this dataset.`}>
              <Chip
                size="small"
                label={`${ctx.system_label || ''} · ${ctx.stream_label}`}
                sx={{ fontWeight: 600, bgcolor: '#F4ECF9', color: '#6A28A8', border: 'none' }}
              />
            </Tooltip>
          )}
        </Stack>
      </Paper>

      {/* Bucket summary row */}
      <Typography sx={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#6A28A8', fontWeight: 700, mb: 1.25 }}>
        Fill-rate distribution
      </Typography>
      <Grid container spacing={1.25} sx={{ mb: 2.5 }}>
        {(s.buckets || []).map((b) => (
          <Grid item xs={6} sm={4} md={2.4} key={b.label}>
            <BucketCard label={b.label} count={b.count} />
          </Grid>
        ))}
      </Grid>

      {/* Filter row */}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems={{ xs: 'stretch', sm: 'center' }} sx={{ mb: 1.5 }}>
        <TextField
          size="small"
          placeholder="Filter by field name or semantic type…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          }}
          sx={{ minWidth: 280, flex: 1 }}
        />
        <FormControlLabel
          control={<Switch size="small" checked={issuesOnly} onChange={(e) => setIssuesOnly(e.target.checked)} />}
          label={<Typography variant="caption" sx={{ fontWeight: 600 }}>Issues only</Typography>}
          sx={{ mx: 0 }}
        />
        <FormControlLabel
          control={<Switch size="small" checked={cdeOnly} onChange={(e) => setCdeOnly(e.target.checked)} />}
          label={<Typography variant="caption" sx={{ fontWeight: 600 }}>CDEs only</Typography>}
          sx={{ mx: 0 }}
        />
      </Stack>

      {/* Field-level table */}
      <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 540 }}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', width: 50 }}>#</TableCell>
              <TableCell sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Critical data element</TableCell>
              <TableCell sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Semantic type</TableCell>
              <TableCell sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em' }} align="right">Filled</TableCell>
              <TableCell sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em' }} align="right">Blank</TableCell>
              <TableCell sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Fill rate</TableCell>
              <TableCell sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {fields.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} sx={{ color: '#8A8A8A', textAlign: 'center', py: 3 }}>
                  No fields match your filter.
                </TableCell>
              </TableRow>
            )}
            {fields.map((f) => {
              const tone = STATUS_STYLE[f.status] || STATUS_STYLE.Acceptable;
              return (
                <TableRow key={f.field} hover>
                  <TableCell sx={{ color: '#8A8A8A', fontVariantNumeric: 'tabular-nums' }}>{f.rank}</TableCell>
                  <TableCell sx={{ py: 0.85 }}>
                    <Stack direction="row" spacing={0.75} alignItems="center">
                      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.84rem', fontWeight: 600 }}>{f.field}</Typography>
                      {f.is_cde && (
                        <Tooltip title="Critical Data Element — AI flagged this column as a business-critical identifier or attribute.">
                          <StarOutlineRoundedIcon sx={{ fontSize: 16, color: '#6A28A8' }} />
                        </Tooltip>
                      )}
                    </Stack>
                  </TableCell>
                  <TableCell sx={{ color: '#475569', fontSize: '0.8rem' }}>
                    {f.semantic_type || <span style={{ color: '#CBD5E1' }}>—</span>}
                  </TableCell>
                  <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums', fontSize: '0.82rem' }}>
                    {(f.filled || 0).toLocaleString()}
                  </TableCell>
                  <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums', fontSize: '0.82rem', color: f.blank > 0 ? '#7F1D1D' : '#8A8A8A' }}>
                    {(f.blank || 0).toLocaleString()}
                  </TableCell>
                  <TableCell sx={{ minWidth: 160 }}>
                    <FillBar pct={f.fill_rate} status={f.status} />
                  </TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={f.status}
                      sx={{
                        height: 22,
                        fontSize: '0.7rem',
                        fontWeight: 700,
                        color: tone.fg,
                        bgcolor: tone.bg,
                        border: 'none',
                      }}
                    />
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}
