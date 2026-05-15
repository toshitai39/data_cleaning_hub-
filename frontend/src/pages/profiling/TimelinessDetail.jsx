import { useEffect, useState } from 'react';
import {
  Box, Typography, Paper, Chip, Stack, Alert, LinearProgress,
  Table, TableHead, TableBody, TableRow, TableCell, TableContainer,
  Accordion, AccordionSummary, AccordionDetails,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import api from '../../api.js';
import { useDataset } from '../../context/DatasetContext.jsx';

function MetricBlock({ label, value, accent }) {
  return (
    <Box>
      <Typography sx={{ fontSize: '0.66rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#8A8A8A' }}>
        {label}
      </Typography>
      <Typography sx={{
        fontFamily: "'Montserrat', sans-serif",
        fontWeight: 700, fontSize: 26, lineHeight: 1,
        color: accent || '#1A1A1A',
      }}>
        {value}
      </Typography>
    </Box>
  );
}

export default function TimelinessDetail() {
  const { state } = useDataset();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .get('/profile/timeliness', { params: { source: 'current' } })
      .then(({ data }) => { if (!cancelled) setData(data); })
      .catch((e) => { if (!cancelled) setErr(e?.response?.data?.detail || 'Failed to compute timeliness'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [state.operations]);

  if (loading) return <LinearProgress />;
  if (err) return <Alert severity="error">{err}</Alert>;
  if (!data) return null;

  const s = data.summary || {};
  const columns = data.columns || [];

  if (columns.length === 0) {
    return (
      <Alert severity="info">
        No date or datetime columns in this dataset — Timeliness has nothing to evaluate.
        Timeliness scores how recent and how plausible the date values are, so it's only
        meaningful for tables with at least one date column (created_at, updated_at,
        effective_date, expiry_date, etc.).
      </Alert>
    );
  }

  return (
    <Box>
      <Paper variant="outlined" sx={{ p: 2, mb: 2, bgcolor: '#FBFAFC' }}>
        <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>
          <MetricBlock label="Overall timeliness" value={`${((s.overall_timeliness || 0) * 100).toFixed(1)}%`} />
          <MetricBlock label="Date columns" value={s.date_columns || 0} />
          <MetricBlock
            label="Future-dated rows"
            value={(s.total_future_rows || 0).toLocaleString()}
            accent={s.total_future_rows > 0 ? '#7F1D1D' : undefined}
          />
          <MetricBlock
            label="Very old (pre-1990)"
            value={(s.total_very_old_rows || 0).toLocaleString()}
            accent={s.total_very_old_rows > 0 ? '#7F5F00' : undefined}
          />
        </Stack>
      </Paper>

      <Typography sx={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#6A28A8', fontWeight: 700, mb: 1 }}>
        Per-column timeliness
      </Typography>
      <TableContainer component={Paper} variant="outlined" sx={{ mb: 2 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Column</TableCell>
              <TableCell align="right" sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Populated</TableCell>
              <TableCell align="right" sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Blank</TableCell>
              <TableCell sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Oldest</TableCell>
              <TableCell sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Newest</TableCell>
              <TableCell align="right" sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Future</TableCell>
              <TableCell align="right" sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Very old</TableCell>
              <TableCell sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Timeliness</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {columns.map((c) => {
              const tone = c.timeliness_rate >= 0.99
                ? { fg: '#0E5226', bg: '#DCFCE7' }
                : c.timeliness_rate >= 0.90
                  ? { fg: '#7F5F00', bg: '#FEF3C7' }
                  : { fg: '#7F1D1D', bg: '#FBEAEA' };
              return (
                <TableRow key={c.column} hover>
                  <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.84rem', fontWeight: 600 }}>{c.column}</TableCell>
                  <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>{c.populated.toLocaleString()}</TableCell>
                  <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums', color: c.blank > 0 ? '#7F1D1D' : '#8A8A8A' }}>
                    {c.blank.toLocaleString()}
                  </TableCell>
                  <TableCell sx={{ fontSize: '0.82rem', color: '#475569' }}>{c.oldest ? c.oldest.slice(0, 10) : '—'}</TableCell>
                  <TableCell sx={{ fontSize: '0.82rem', color: '#475569' }}>{c.newest ? c.newest.slice(0, 10) : '—'}</TableCell>
                  <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums', color: c.future_dated > 0 ? '#7F1D1D' : '#8A8A8A', fontWeight: c.future_dated > 0 ? 700 : 400 }}>
                    {c.future_dated.toLocaleString()}
                  </TableCell>
                  <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums', color: c.very_old > 0 ? '#7F5F00' : '#8A8A8A', fontWeight: c.very_old > 0 ? 700 : 400 }}>
                    {c.very_old.toLocaleString()}
                  </TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={`${(c.timeliness_rate * 100).toFixed(1)}%`}
                      sx={{ height: 22, fontSize: '0.7rem', fontWeight: 700, color: tone.fg, bgcolor: tone.bg, border: 'none' }}
                    />
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Sample suspicious rows per column */}
      {columns.filter((c) => (c.samples_future || []).length > 0 || (c.samples_very_old || []).length > 0).length > 0 && (
        <>
          <Typography sx={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#6A28A8', fontWeight: 700, mb: 1 }}>
            Suspicious-date samples
          </Typography>
          {columns.filter((c) => (c.samples_future || []).length > 0 || (c.samples_very_old || []).length > 0).map((c) => (
            <Accordion
              key={`acc-${c.column}`}
              disableGutters
              elevation={0}
              sx={{ border: '1px solid', borderColor: 'divider', '&:before': { display: 'none' }, mb: 0.75 }}
            >
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Stack direction="row" spacing={1.5} alignItems="center">
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.86rem', fontWeight: 700 }}>{c.column}</Typography>
                  {c.future_dated > 0 && (
                    <Chip size="small" label={`${c.future_dated} future-dated`} sx={{ height: 18, fontSize: '0.66rem', fontWeight: 700, color: '#7F1D1D', bgcolor: '#FBEAEA', border: 'none' }} />
                  )}
                  {c.very_old > 0 && (
                    <Chip size="small" label={`${c.very_old} very old`} sx={{ height: 18, fontSize: '0.66rem', fontWeight: 700, color: '#7F5F00', bgcolor: '#FEF3C7', border: 'none' }} />
                  )}
                </Stack>
              </AccordionSummary>
              <AccordionDetails>
                {(c.samples_future || []).length > 0 && (
                  <Box sx={{ mb: 1.5 }}>
                    <Typography sx={{ fontSize: '0.7rem', fontWeight: 700, color: '#7F1D1D', mb: 0.5 }}>Future-dated samples</Typography>
                    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                      {c.samples_future.map((s, i) => (
                        <Chip key={i} size="small" label={`Row ${s.row} · ${s.value.slice(0, 19)}`} sx={{ fontFamily: 'monospace', fontSize: '0.74rem', bgcolor: '#FFFFFF', border: '1px solid #FCA5A5' }} />
                      ))}
                    </Stack>
                  </Box>
                )}
                {(c.samples_very_old || []).length > 0 && (
                  <Box>
                    <Typography sx={{ fontSize: '0.7rem', fontWeight: 700, color: '#7F5F00', mb: 0.5 }}>Very old samples (pre-1990)</Typography>
                    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                      {c.samples_very_old.map((s, i) => (
                        <Chip key={i} size="small" label={`Row ${s.row} · ${s.value.slice(0, 19)}`} sx={{ fontFamily: 'monospace', fontSize: '0.74rem', bgcolor: '#FFFFFF', border: '1px solid #FDE68A' }} />
                      ))}
                    </Stack>
                  </Box>
                )}
              </AccordionDetails>
            </Accordion>
          ))}
        </>
      )}
    </Box>
  );
}
