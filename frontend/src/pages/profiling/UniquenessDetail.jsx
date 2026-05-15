import { useEffect, useRef, useState } from 'react';
import {
  Box, Typography, Paper, Chip, Stack, Alert, LinearProgress, Button,
  Table, TableHead, TableBody, TableRow, TableCell, TableContainer, Tooltip,
  Accordion, AccordionSummary, AccordionDetails, CircularProgress,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import AutoAwesomeOutlinedIcon from '@mui/icons-material/AutoAwesomeOutlined';
import api from '../../api.js';
import { useDataset } from '../../context/DatasetContext.jsx';

const SEVERITY_TONE = {
  high:          { fg: '#7F1D1D', bg: '#FBEAEA', label: 'High risk' },
  medium:        { fg: '#7F5F00', bg: '#FEF3C7', label: 'Medium' },
  informational: { fg: '#0E5226', bg: '#ECFDF5', label: 'Informational' },
};

function MetricBlock({ label, value, accent, tooltip }) {
  const content = (
    <Box sx={tooltip ? { cursor: 'help' } : undefined}>
      <Typography sx={{ fontSize: '0.66rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#8A8A8A' }}>
        {label}{tooltip && <span style={{ marginLeft: 4, color: '#6A28A8' }}>ⓘ</span>}
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
  if (tooltip) {
    return (
      <Tooltip title={tooltip} placement="bottom-start" arrow>
        {content}
      </Tooltip>
    );
  }
  return content;
}

export default function UniquenessDetail() {
  const { state } = useDataset();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [classifying, setClassifying] = useState(false);
  const [classifyErr, setClassifyErr] = useState('');
  // Guard so we auto-classify at most once per mount — keeps us from
  // re-triggering an expensive LLM call if the user navigates back and
  // forth between drill-downs.
  const autoClassifiedRef = useRef(false);

  const fetchUniqueness = async () => {
    setLoading(true);
    setErr('');
    try {
      const { data } = await api.get('/profile/uniqueness', { params: { source: 'current' } });
      setData(data);
      return data;
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Failed to compute uniqueness');
      return null;
    } finally {
      setLoading(false);
    }
  };

  const runClassification = async () => {
    setClassifying(true);
    setClassifyErr('');
    try {
      await api.post('/data/columns-of-interest/generate-glossary');
      await fetchUniqueness();
    } catch (e) {
      setClassifyErr(e?.response?.data?.detail || 'AI classification failed');
    } finally {
      setClassifying(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const result = await fetchUniqueness();
      if (cancelled || !result) return;
      // If the backend signals no classification exists yet, trigger the
      // recommender silently so the AI's per-column understanding flows
      // through to this view without making the steward click anything.
      if (result.needs_classification && !autoClassifiedRef.current) {
        autoClassifiedRef.current = true;
        await runClassification();
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.operations]);

  if (loading && !data) return <LinearProgress />;
  if (err) return <Alert severity="error">{err}</Alert>;
  if (!data) return null;

  const s = data.summary || {};
  const ck = data.composite_key_duplicates || {};
  const ctx = data.project_context || {};
  const hasIdentifiers = (s.identifier_columns || []).length > 0;

  if (!hasIdentifiers) {
    const needsClassification = data.needs_classification || classifying;
    return (
      <Paper variant="outlined" sx={{ p: 3, bgcolor: '#FBFAFC' }}>
        <Stack alignItems="center" textAlign="center" spacing={1}>
          <AutoAwesomeOutlinedIcon sx={{ fontSize: 36, color: '#6A28A8' }} />
          <Typography sx={{ fontFamily: "'Montserrat', sans-serif", fontWeight: 700, fontSize: 18 }}>
            {classifying ? 'Classifying columns with AI…' : needsClassification ? 'Refreshing AI classification…' : 'No identifier columns in this dataset'}
          </Typography>
          <Typography sx={{ fontSize: 14, color: '#475569', maxWidth: 640 }}>
            {classifying
              ? 'One batched call against all in-scope columns to map each one to a semantic type (pan / gstin / numeric_id / iso_country / etc.). Usually 10–25 seconds.'
              : needsClassification
                ? 'Identifying which columns are entity keys so Uniqueness knows what to test on. This is auto-triggered the first time you visit any dimension drill-down.'
                : 'The AI classified your columns but none came back as identifier-type. Uniqueness has nothing to test — Completeness, Validation and Standardisation still cover these fields.'}
          </Typography>
        </Stack>
        {classifying && <LinearProgress sx={{ mt: 2 }} />}
        {!classifying && (
          <Box sx={{ textAlign: 'center', mt: 2.5 }}>
            <Button
              variant="outlined"
              size="small"
              startIcon={<AutoAwesomeOutlinedIcon sx={{ fontSize: 16 }} />}
              onClick={runClassification}
            >
              {needsClassification ? 'Generate AI classification' : 'Regenerate AI classification'}
            </Button>
          </Box>
        )}
        {classifyErr && <Alert severity="error" sx={{ mt: 2 }}>{classifyErr}</Alert>}
      </Paper>
    );
  }

  return (
    <Box>
      <Paper variant="outlined" sx={{ p: 2, mb: 2, bgcolor: '#FBFAFC' }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={3} justifyContent="space-between" alignItems="flex-start">
          <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>
            <MetricBlock label="Total Rows" value={(s.rows || 0).toLocaleString()} />
            <MetricBlock label="Distinct Rows" value={(s.distinct_rows || 0).toLocaleString()} />
            <MetricBlock label="Full-Row Duplicates" value={(s.full_row_duplicates || 0).toLocaleString()} accent={s.full_row_duplicates > 0 ? '#7F1D1D' : undefined} />
            <MetricBlock
              label="Primary Identifier"
              value={s.primary_identifier || '—'}
              tooltip={s.primary_rationale || 'Identifier ranking: generic-ID types (alphanumeric_id / numeric_id) outrank regulatory IDs (PAN / GSTIN / TAN). Within a tier we prefer higher actual uniqueness, then source-column order as the final tiebreaker.'}
            />
          </Stack>
          {ctx.stream_label && (
            <Chip
              size="small"
              label={`${ctx.system_label || ''} · ${ctx.stream_label}`}
              sx={{ fontWeight: 600, bgcolor: '#F4ECF9', color: '#6A28A8', border: 'none' }}
            />
          )}
        </Stack>
      </Paper>

      {/* Composite-key duplicate analysis */}
      {ck.key && ck.key.length > 0 && (
        <>
          <Typography sx={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#6A28A8', fontWeight: 700, mb: 0.5 }}>
            Duplicate {ck.key.join(' + ')} combinations
          </Typography>
          <Typography sx={{ fontSize: '0.78rem', color: '#475569', mb: 1.25 }}>
            {ck.fallback_used
              ? `No name / regulatory-ID columns detected in this dataset — composite falls back to "${ck.key.join(' + ')}", which means the check is dominated by columns that are already 100% unique. Limited diagnostic value here; see "Shared identifiers across multiple entity rows" below for the real signal.`
              : `Looks for rows that share the same ${ck.key.join(' + ')} but were recorded under a different primary identifier (${s.primary_identifier || 'entity key'}). Catches duplicate entity records masquerading under different keys.`}
          </Typography>
          <Paper variant="outlined" sx={{ p: 2, mb: 2.5, bgcolor: '#FFFFFF' }}>
            <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>
              <MetricBlock label="Duplicate combos" value={ck.duplicate_combos.toLocaleString()} accent={ck.duplicate_combos > 0 ? '#7F1D1D' : undefined} />
              <MetricBlock label="Rows in duplicates" value={ck.rows_in_duplicates.toLocaleString()} />
              <MetricBlock label="Duplicate rate" value={`${(ck.duplicate_rate * 100).toFixed(1)}%`} />
            </Stack>
            {(ck.samples || []).length > 0 && (
              <TableContainer sx={{ mt: 2 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      {ck.key.map((c) => (
                        <TableCell key={c} sx={{ fontWeight: 700, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A' }}>{c}</TableCell>
                      ))}
                      <TableCell align="right" sx={{ fontWeight: 700, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A' }}>Rows</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {ck.samples.map((row, i) => (
                      <TableRow key={i}>
                        {ck.key.map((c) => (
                          <TableCell key={c} sx={{ fontFamily: 'monospace', fontSize: '0.84rem' }}>
                            {row.values[c] || <span style={{ color: '#CBD5E1' }}>—</span>}
                          </TableCell>
                        ))}
                        <TableCell align="right" sx={{ fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
                          {row.rows}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </Paper>
        </>
      )}

      {/* Shared identifier risk */}
      {(data.shared_identifier_risk || []).length > 0 && (
        <>
          <Typography sx={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#6A28A8', fontWeight: 700, mb: 1 }}>
            Shared identifiers across multiple entity rows
          </Typography>
          {data.shared_identifier_risk.map((risk) => {
            const tone = SEVERITY_TONE[risk.severity] || SEVERITY_TONE.medium;
            return (
              <Accordion
                key={risk.column}
                disableGutters
                elevation={0}
                sx={{ border: '1px solid', borderColor: 'divider', '&:before': { display: 'none' }, mb: 0.75 }}
              >
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Stack direction="row" spacing={1.5} alignItems="center" sx={{ width: '100%' }}>
                    <Typography sx={{ fontFamily: 'monospace', fontSize: '0.86rem', fontWeight: 700 }}>{risk.column}</Typography>
                    <Chip
                      size="small"
                      label={(risk.semantic_type || 'identifier').toUpperCase()}
                      sx={{ height: 18, fontSize: '0.66rem', fontWeight: 700, color: '#6A28A8', bgcolor: '#F4ECF9', border: 'none' }}
                    />
                    <Chip
                      size="small"
                      label={tone.label}
                      sx={{ height: 20, fontSize: '0.68rem', fontWeight: 700, color: tone.fg, bgcolor: tone.bg, border: 'none' }}
                    />
                    <Typography sx={{ fontSize: '0.82rem', color: '#475569' }}>
                      <b>{risk.shared_values}</b> value{risk.shared_values === 1 ? '' : 's'} shared across <b>{risk.rows_affected.toLocaleString()}</b> rows
                    </Typography>
                  </Stack>
                </AccordionSummary>
                <AccordionDetails>
                  <TableContainer>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell sx={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A', fontWeight: 700 }}>Value</TableCell>
                          <TableCell sx={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A', fontWeight: 700 }} align="right"># distinct entities</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {(risk.samples || []).map((sample, i) => (
                          <TableRow key={i}>
                            <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.84rem' }}>{sample.value}</TableCell>
                            <TableCell align="right" sx={{ fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{sample.distinct_entities}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </AccordionDetails>
              </Accordion>
            );
          })}
        </>
      )}

      {/* Per-column uniqueness rollup */}
      {(data.per_column || []).length > 0 && (
        <>
          <Typography sx={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#6A28A8', fontWeight: 700, mt: 3, mb: 1 }}>
            Per-identifier uniqueness
          </Typography>
          <TableContainer component={Paper} variant="outlined">
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 700, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A' }}>Column</TableCell>
                  <TableCell sx={{ fontWeight: 700, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A' }}>Type</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A' }}>Non-null</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A' }}>Unique</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A' }}>Duplicates</TableCell>
                  <TableCell sx={{ fontWeight: 700, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A' }}>Uniqueness</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.per_column.map((row) => (
                  <TableRow key={row.column} hover>
                    <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.84rem', fontWeight: 600 }}>{row.column}</TableCell>
                    <TableCell sx={{ color: '#475569', fontSize: '0.8rem' }}>{row.semantic_type || '—'}</TableCell>
                    <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>{row.non_null.toLocaleString()}</TableCell>
                    <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>{row.unique.toLocaleString()}</TableCell>
                    <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums', color: row.duplicates > 0 ? '#7F1D1D' : '#8A8A8A', fontWeight: row.duplicates > 0 ? 700 : 400 }}>
                      {row.duplicates.toLocaleString()}
                    </TableCell>
                    <TableCell>
                      {row.is_empty || row.uniqueness_rate == null ? (
                        <Tooltip title="Column is entirely blank in this dataset — uniqueness can't be measured. Completeness covers this finding separately.">
                          <Chip
                            size="small"
                            label="All blank"
                            sx={{ height: 22, fontSize: '0.7rem', fontWeight: 700, color: '#475569', bgcolor: '#F1F5F9', border: 'none' }}
                          />
                        </Tooltip>
                      ) : (
                        <Chip
                          size="small"
                          label={`${(row.uniqueness_rate * 100).toFixed(1)}%`}
                          sx={{
                            height: 22, fontSize: '0.7rem', fontWeight: 700,
                            color: row.uniqueness_rate >= 0.99 ? '#0E5226' : row.uniqueness_rate >= 0.90 ? '#7F5F00' : '#7F1D1D',
                            bgcolor: row.uniqueness_rate >= 0.99 ? '#DCFCE7' : row.uniqueness_rate >= 0.90 ? '#FEF3C7' : '#FBEAEA',
                            border: 'none',
                          }}
                        />
                      )}
                    </TableCell>
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
