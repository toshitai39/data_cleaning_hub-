import { useEffect, useState } from 'react';
import {
  Box, Typography, Paper, Chip, Stack, Alert, LinearProgress,
  Table, TableHead, TableBody, TableRow, TableCell, TableContainer, Tooltip,
  Accordion, AccordionSummary, AccordionDetails,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import api from '../../api.js';

const CASE_TONE = {
  upper: '#0E5226', lower: '#1E3A8A', title: '#7F5F00', mixed: '#7F1D1D', other: '#475569',
};

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

function CaseStack({ counts, dominant }) {
  const total = ['upper', 'lower', 'title', 'mixed', 'other'].reduce((acc, k) => acc + (counts[k] || 0), 0);
  if (!total) return null;
  return (
    <Box sx={{ display: 'flex', height: 8, borderRadius: 1, overflow: 'hidden', minWidth: 140 }}>
      {['upper', 'lower', 'title', 'mixed', 'other'].map((k) => {
        const v = counts[k] || 0;
        if (!v) return null;
        return (
          <Tooltip key={k} title={`${k}: ${v}${k === dominant ? ' (dominant)' : ''}`}>
            <Box sx={{ width: `${(v / total) * 100}%`, bgcolor: CASE_TONE[k], opacity: k === dominant ? 1 : 0.55 }} />
          </Tooltip>
        );
      })}
    </Box>
  );
}

export default function StandardisationDetail() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .get('/profile/standardisation')
      .then(({ data }) => { if (!cancelled) setData(data); })
      .catch((e) => { if (!cancelled) setErr(e?.response?.data?.detail || 'Failed to compute standardisation'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  if (loading) return <LinearProgress />;
  if (err) return <Alert severity="error">{err}</Alert>;
  if (!data) return null;

  const s = data.summary || {};
  const hasText = (data.case_patterns || []).length > 0;

  if (!hasText) {
    return (
      <Alert severity="info">
        No text columns were found to standardise on. Standardisation inspects free-text /
        enum / country / currency columns — identifier columns (PAN / GSTIN / Email) are
        covered by Validation instead.
      </Alert>
    );
  }

  return (
    <Box>
      <Paper variant="outlined" sx={{ p: 2, mb: 2, bgcolor: '#FBFAFC' }}>
        <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>
          <MetricBlock label="Overall consistency" value={`${((s.overall_consistency || 0) * 100).toFixed(1)}%`} />
          <MetricBlock label="Text columns" value={s.text_columns || 0} />
          <MetricBlock label="Off-pattern values" value={(s.off_pattern_values || 0).toLocaleString()} accent={s.off_pattern_values > 0 ? '#7F1D1D' : undefined} />
          <MetricBlock label="Spelling-variant cols" value={s.spelling_variant_columns || 0} accent={s.spelling_variant_columns > 0 ? '#7F1D1D' : undefined} />
          <MetricBlock label="Whitespace-issue cols" value={s.whitespace_issue_columns || 0} accent={s.whitespace_issue_columns > 0 ? '#7F5F00' : undefined} />
        </Stack>
      </Paper>

      {/* Case patterns */}
      <Typography sx={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#6A28A8', fontWeight: 700, mb: 1 }}>
        Case patterns
      </Typography>
      <TableContainer component={Paper} variant="outlined" sx={{ mb: 3 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A' }}>Column</TableCell>
              <TableCell sx={{ fontWeight: 700, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A' }}>Dominant</TableCell>
              <TableCell sx={{ fontWeight: 700, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A' }}>Composition</TableCell>
              <TableCell align="right" sx={{ fontWeight: 700, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A' }}>Off-pattern</TableCell>
              <TableCell sx={{ fontWeight: 700, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A' }}>Consistency</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data.case_patterns.map((c) => {
              const tone = c.consistency_rate >= 0.99 ? { fg: '#0E5226', bg: '#DCFCE7' }
                       : c.consistency_rate >= 0.90 ? { fg: '#7F5F00', bg: '#FEF3C7' }
                       :                              { fg: '#7F1D1D', bg: '#FBEAEA' };
              return (
                <TableRow key={c.column} hover>
                  <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.84rem', fontWeight: 600 }}>{c.column}</TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={c.dominant}
                      sx={{ height: 20, fontSize: '0.68rem', fontWeight: 700, color: CASE_TONE[c.dominant], bgcolor: '#F1F5F9', border: 'none', textTransform: 'uppercase' }}
                    />
                  </TableCell>
                  <TableCell sx={{ minWidth: 160 }}>
                    <CaseStack counts={c.counts} dominant={c.dominant} />
                  </TableCell>
                  <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums', color: c.off_pattern > 0 ? '#7F1D1D' : '#8A8A8A', fontWeight: c.off_pattern > 0 ? 700 : 400 }}>
                    {c.off_pattern.toLocaleString()}
                  </TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={`${(c.consistency_rate * 100).toFixed(1)}%`}
                      sx={{ height: 22, fontSize: '0.7rem', fontWeight: 700, color: tone.fg, bgcolor: tone.bg, border: 'none' }}
                    />
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Spelling variants */}
      {(data.spelling_variants || []).length > 0 && (
        <>
          <Typography sx={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#6A28A8', fontWeight: 700, mb: 1 }}>
            Spelling-variant clusters
          </Typography>
          <Typography sx={{ fontSize: '0.78rem', color: '#475569', mb: 1.5 }}>
            Values that normalise to the same form but are spelled differently (whitespace, hyphens,
            accents, case) — typical case is the same city or company name entered multiple ways.
          </Typography>
          {data.spelling_variants.map((sv) => (
            <Accordion
              key={sv.column}
              disableGutters
              elevation={0}
              sx={{ border: '1px solid', borderColor: 'divider', '&:before': { display: 'none' }, mb: 0.75 }}
            >
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Stack direction="row" spacing={1.5} alignItems="center">
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.86rem', fontWeight: 700 }}>{sv.column}</Typography>
                  {sv.semantic_type && (
                    <Chip
                      size="small"
                      label={sv.semantic_type}
                      sx={{ height: 18, fontSize: '0.66rem', fontWeight: 700, color: '#6A28A8', bgcolor: '#F4ECF9', border: 'none' }}
                    />
                  )}
                  <Typography sx={{ fontSize: '0.82rem', color: '#7F1D1D', fontWeight: 600 }}>
                    {sv.clusters.length} variant cluster{sv.clusters.length === 1 ? '' : 's'}
                  </Typography>
                </Stack>
              </AccordionSummary>
              <AccordionDetails>
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell sx={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A', fontWeight: 700, width: 120 }}>Normalised form</TableCell>
                        <TableCell sx={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A', fontWeight: 700 }}>Variants found</TableCell>
                        <TableCell align="right" sx={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A', fontWeight: 700, width: 80 }}>Rows</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {sv.clusters.map((cl, i) => (
                        <TableRow key={i}>
                          <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.8rem', color: '#475569' }}>{cl.normalised}</TableCell>
                          <TableCell>
                            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                              {cl.variants.map((v, j) => (
                                <Chip
                                  key={j}
                                  size="small"
                                  label={`${v.value} (${v.count})`}
                                  sx={{ height: 22, fontSize: '0.74rem', bgcolor: '#FFFFFF', border: '1px solid #DDD6E5', fontFamily: 'monospace' }}
                                />
                              ))}
                            </Stack>
                          </TableCell>
                          <TableCell align="right" sx={{ fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
                            {cl.total_rows.toLocaleString()}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </AccordionDetails>
            </Accordion>
          ))}
        </>
      )}

      {/* Whitespace / control-character issues */}
      {(data.whitespace || []).length > 0 && (
        <>
          <Typography sx={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#6A28A8', fontWeight: 700, mt: 3, mb: 1 }}>
            Whitespace &amp; non-printable characters
          </Typography>
          <TableContainer component={Paper} variant="outlined">
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 700, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A' }}>Column</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A' }}>Leading space</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A' }}>Trailing space</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A' }}>Double-space</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A' }}>Control chars</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.whitespace.map((w) => (
                  <TableRow key={w.column} hover>
                    <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.84rem', fontWeight: 600 }}>{w.column}</TableCell>
                    <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums', color: w.leading > 0 ? '#7F1D1D' : '#8A8A8A' }}>{w.leading.toLocaleString()}</TableCell>
                    <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums', color: w.trailing > 0 ? '#7F1D1D' : '#8A8A8A' }}>{w.trailing.toLocaleString()}</TableCell>
                    <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums', color: w.doublespace > 0 ? '#7F1D1D' : '#8A8A8A' }}>{w.doublespace.toLocaleString()}</TableCell>
                    <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums', color: w.control_chars > 0 ? '#7F1D1D' : '#8A8A8A' }}>{w.control_chars.toLocaleString()}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </>
      )}
    </Box>
  );
}
