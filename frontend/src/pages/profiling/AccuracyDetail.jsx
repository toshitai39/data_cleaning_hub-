import { useEffect, useState } from 'react';
import {
  Box, Typography, Paper, Chip, Stack, Alert, LinearProgress,
  Table, TableHead, TableBody, TableRow, TableCell, TableContainer, Tooltip,
  Accordion, AccordionSummary, AccordionDetails,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import RuleOutlinedIcon from '@mui/icons-material/RuleOutlined';
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

export default function AccuracyDetail() {
  const { state } = useDataset();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .get('/profile/accuracy', { params: { source: 'current' } })
      .then(({ data }) => { if (!cancelled) setData(data); })
      .catch((e) => { if (!cancelled) setErr(e?.response?.data?.detail || 'Failed to compute accuracy'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [state.operations]);

  if (loading) return <LinearProgress />;
  if (err) return <Alert severity="error">{err}</Alert>;
  if (!data) return null;

  const s = data.summary || {};
  const rules = data.rules || [];

  if (data.needs_rules) {
    return (
      <Paper variant="outlined" sx={{ p: 3, textAlign: 'center', bgcolor: '#FBFAFC' }}>
        <RuleOutlinedIcon sx={{ fontSize: 36, color: '#6A28A8', mb: 1 }} />
        <Typography sx={{ fontFamily: "'Montserrat', sans-serif", fontWeight: 700, fontSize: 18, mb: 0.75 }}>
          Accuracy needs cross-field rules to score
        </Typography>
        <Typography sx={{ fontSize: 14, color: '#475569', mb: 1.5, maxWidth: 640, mx: 'auto' }}>
          Accuracy measures whether multi-column business rules hold (e.g. <i>GST Registered = Yes ⇒ GSTIN must be populated</i>).
          Generate cross-field rules on <b>Rule Generator</b>, then come back here to see per-rule violations and failing-row samples.
        </Typography>
      </Paper>
    );
  }

  return (
    <Box>
      <Paper variant="outlined" sx={{ p: 2, mb: 2, bgcolor: '#FBFAFC' }}>
        <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>
          <MetricBlock label="Pass rate" value={`${((s.pass_rate || 0) * 100).toFixed(1)}%`} />
          <MetricBlock label="Total rules" value={s.total_rules || 0} />
          <MetricBlock label="Rules passing" value={s.rules_passing || 0} accent="#0E5226" />
          <MetricBlock label="Rules failing" value={s.rules_failing || 0} accent={s.rules_failing > 0 ? '#7F1D1D' : undefined} />
          <MetricBlock label="Total violations" value={(s.total_violations || 0).toLocaleString()} accent={s.total_violations > 0 ? '#7F1D1D' : undefined} />
        </Stack>
      </Paper>

      <Typography sx={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#6A28A8', fontWeight: 700, mb: 1 }}>
        Cross-field rules — failing first
      </Typography>
      <TableContainer component={Paper} variant="outlined" sx={{ mb: 2 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', width: 40 }}>#</TableCell>
              <TableCell sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Rule</TableCell>
              <TableCell sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Columns involved</TableCell>
              <TableCell align="right" sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Issues</TableCell>
              <TableCell sx={{ fontWeight: 700, color: '#8A8A8A', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rules.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} sx={{ color: '#8A8A8A', textAlign: 'center', py: 2 }}>
                  No cross-field rules to report.
                </TableCell>
              </TableRow>
            )}
            {rules.map((r) => {
              const tone = r.status === 'Passing'
                ? { fg: '#0E5226', bg: '#DCFCE7' }
                : { fg: '#7F1D1D', bg: '#FBEAEA' };
              return (
                <TableRow key={r.id} hover>
                  <TableCell sx={{ color: '#8A8A8A', fontVariantNumeric: 'tabular-nums' }}>{r.id}</TableCell>
                  <TableCell sx={{ fontSize: '0.84rem', fontWeight: 500 }}>{r.rule_text}</TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                      {r.columns.map((c) => (
                        <Chip
                          key={c}
                          size="small"
                          label={c}
                          sx={{ height: 20, fontSize: '0.7rem', fontFamily: 'monospace', bgcolor: '#FFFFFF', border: '1px solid #DDD6E5' }}
                        />
                      ))}
                    </Stack>
                  </TableCell>
                  <TableCell align="right" sx={{
                    fontVariantNumeric: 'tabular-nums', fontSize: '0.84rem',
                    color: r.issues_found > 0 ? '#7F1D1D' : '#8A8A8A',
                    fontWeight: r.issues_found > 0 ? 700 : 400,
                  }}>
                    {r.issues_found.toLocaleString()}
                  </TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={r.status}
                      sx={{ height: 22, fontSize: '0.7rem', fontWeight: 700, color: tone.fg, bgcolor: tone.bg, border: 'none' }}
                    />
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Per-rule failing-example drill-down */}
      {rules.filter((r) => r.status === 'Failing' && (r.example || r.validation_expression)).length > 0 && (
        <>
          <Typography sx={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#6A28A8', fontWeight: 700, mb: 1 }}>
            Failing-rule samples &amp; expressions
          </Typography>
          {rules.filter((r) => r.status === 'Failing' && (r.example || r.validation_expression)).map((r) => (
            <Accordion
              key={`acc-${r.id}`}
              disableGutters
              elevation={0}
              sx={{ border: '1px solid', borderColor: 'divider', '&:before': { display: 'none' }, mb: 0.75 }}
            >
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Stack direction="row" spacing={1.5} alignItems="center" sx={{ width: '100%' }}>
                  <Typography sx={{ fontSize: '0.86rem', fontWeight: 700 }}>{r.rule_text}</Typography>
                  <Typography sx={{ fontSize: '0.78rem', color: '#7F1D1D', fontWeight: 600 }}>
                    {r.issues_found.toLocaleString()} violations
                  </Typography>
                </Stack>
              </AccordionSummary>
              <AccordionDetails>
                {r.validation_expression && (
                  <Box sx={{ mb: 1.5 }}>
                    <Typography sx={{ fontSize: '0.66rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#8A8A8A' }}>
                      Validation expression
                    </Typography>
                    <Typography sx={{ fontFamily: 'monospace', fontSize: '0.84rem', mt: 0.5, p: 1, bgcolor: '#F1F5F9', borderRadius: 1, color: '#1A1A1A' }}>
                      {r.validation_expression}
                    </Typography>
                  </Box>
                )}
                {r.example && (
                  <Box>
                    <Typography sx={{ fontSize: '0.66rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#8A8A8A' }}>
                      Sample failing values
                    </Typography>
                    <Typography sx={{ fontFamily: 'monospace', fontSize: '0.82rem', mt: 0.5, color: '#7F1D1D' }}>
                      {r.example}
                    </Typography>
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
