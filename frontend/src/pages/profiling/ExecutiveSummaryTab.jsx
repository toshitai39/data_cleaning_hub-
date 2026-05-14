import { useEffect, useState } from 'react';
import {
  Box, Typography, Grid, Paper, Chip, Stack, Alert, LinearProgress,
  Divider, Table, TableHead, TableBody, TableRow, TableCell, Link, Breadcrumbs,
} from '@mui/material';
import CheckCircleOutlinedIcon from '@mui/icons-material/CheckCircleOutlined';
import WarningAmberOutlinedIcon from '@mui/icons-material/WarningAmberOutlined';
import ErrorOutlineOutlinedIcon from '@mui/icons-material/ErrorOutlineOutlined';
import HelpOutlineOutlinedIcon from '@mui/icons-material/HelpOutlineOutlined';
import ArrowBackRoundedIcon from '@mui/icons-material/ArrowBackRounded';
import ChevronRightRoundedIcon from '@mui/icons-material/ChevronRightRounded';
import api from '../../api.js';
import CompletenessTab from './CompletenessTab.jsx';
import ValidationDetail from './ValidationDetail.jsx';
import UniquenessDetail from './UniquenessDetail.jsx';
import StandardisationDetail from './StandardisationDetail.jsx';
import AccuracyDetail from './AccuracyDetail.jsx';
import TimelinessDetail from './TimelinessDetail.jsx';

// Every DAMA dimension now has a drill-down. Disabled dimensions still
// land on a detail panel that explains what's missing + offers the
// relevant one-click action (e.g. "Run Rule Generator's cross-field
// pass" inside Accuracy).
const DIMENSION_DETAILS = {
  Completeness:    CompletenessTab,
  Validation:      ValidationDetail,
  Uniqueness:      UniquenessDetail,
  Standardisation: StandardisationDetail,
  Accuracy:        AccuracyDetail,
  Timeliness:      TimelinessDetail,
};

// DAMA dimensions rendered in canonical order. Anything the backend
// returns that we don't have a colour for falls through to a neutral
// slate palette so a future dimension addition still renders cleanly.
const RATING_STYLE = {
  Strong:            { fg: '#0E5226', bg: '#DCFCE7', border: '#86EFAC', icon: CheckCircleOutlinedIcon },
  Moderate:          { fg: '#7F5F00', bg: '#FEF3C7', border: '#FDE68A', icon: WarningAmberOutlinedIcon },
  'Needs Attention': { fg: '#7A4F09', bg: '#FFE4B5', border: '#FED7AA', icon: WarningAmberOutlinedIcon },
  Critical:          { fg: '#7F1D1D', bg: '#FBEAEA', border: '#FCA5A5', icon: ErrorOutlineOutlinedIcon },
  '—':               { fg: '#475569', bg: '#F1F5F9', border: '#CBD5E1', icon: HelpOutlineOutlinedIcon },
};

const RISK_CHIP = {
  Low:    { fg: '#0E5226', bg: '#DCFCE7' },
  Medium: { fg: '#7F5F00', bg: '#FEF3C7' },
  High:   { fg: '#7F1D1D', bg: '#FBEAEA' },
  '—':    { fg: '#475569', bg: '#F1F5F9' },
};

const PRIORITY_STYLE = {
  P1: { fg: '#7F1D1D', bg: '#FBEAEA' },
  P2: { fg: '#7F5F00', bg: '#FEF3C7' },
  P3: { fg: '#0E5226', bg: '#DCFCE7' },
};

function ratingStyle(rating) {
  return RATING_STYLE[rating] || RATING_STYLE['—'];
}

function riskStyle(risk) {
  return RISK_CHIP[risk] || RISK_CHIP['—'];
}


function ScoreCard({ dim, onDrillDown }) {
  const style = ratingStyle(dim.rating);
  const Icon = style.icon;
  const scorePct = dim.enabled ? `${Math.round((dim.score || 0) * 100)}%` : '—';
  const hasDetail = Boolean(DIMENSION_DETAILS[dim.dimension]);
  // Always allow drill-down when a detail view exists — even for a
  // "disabled" dimension. Clicking takes the steward to a panel that
  // can self-heal (e.g. regenerate the AI classification so Validation
  // can score).
  const isClickable = hasDetail;

  return (
    <Paper
      variant="outlined"
      onClick={isClickable ? () => onDrillDown(dim.dimension) : undefined}
      sx={{
        p: 2,
        borderColor: style.border,
        bgcolor: '#FFFFFF',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        gap: 1.25,
        cursor: isClickable ? 'pointer' : 'default',
        transition: 'box-shadow 120ms, transform 120ms',
        '&:hover': isClickable ? {
          boxShadow: '0 6px 18px rgba(73,32,121,0.10)',
          transform: 'translateY(-1px)',
          borderColor: '#6A28A8',
        } : {},
      }}
    >
      <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <Icon sx={{ fontSize: 20, color: style.fg }} />
          <Typography
            sx={{
              fontFamily: "'Montserrat', sans-serif",
              fontWeight: 700,
              fontSize: 15,
              color: '#1A1A1A',
            }}
          >
            {dim.dimension}
          </Typography>
        </Stack>
        <Chip
          size="small"
          label={dim.risk_level}
          sx={{
            height: 22,
            fontSize: '0.7rem',
            fontWeight: 700,
            color: riskStyle(dim.risk_level).fg,
            bgcolor: riskStyle(dim.risk_level).bg,
            border: 'none',
          }}
        />
      </Stack>

      <Stack direction="row" alignItems="baseline" spacing={1.25}>
        <Typography
          sx={{
            fontFamily: "'Montserrat', sans-serif",
            fontSize: 30,
            fontWeight: 700,
            lineHeight: 1,
            color: style.fg,
          }}
        >
          {scorePct}
        </Typography>
        <Chip
          size="small"
          label={dim.rating}
          sx={{
            height: 22,
            fontSize: '0.7rem',
            fontWeight: 700,
            color: style.fg,
            bgcolor: style.bg,
            border: 'none',
          }}
        />
      </Stack>

      <Box sx={{ flex: 1 }}>
        <Typography sx={{ fontSize: '0.78rem', color: '#475569', lineHeight: 1.45 }}>
          {dim.key_finding}
        </Typography>
      </Box>

      <Box>
        <Typography sx={{ fontSize: '0.66rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A', fontWeight: 700 }}>
          Records impacted
        </Typography>
        <Typography sx={{ fontSize: '0.82rem', fontWeight: 600, color: '#1A1A1A' }}>
          {dim.records_impacted}
        </Typography>
      </Box>

      {isClickable && (
        <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mt: 0.5, color: '#6A28A8' }}>
          <Typography sx={{ fontSize: '0.74rem', fontWeight: 700 }}>View detail</Typography>
          <ChevronRightRoundedIcon sx={{ fontSize: 16 }} />
        </Stack>
      )}
    </Paper>
  );
}


export default function ExecutiveSummaryTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  // Master/detail navigation within this tab. null = summary view;
  // otherwise the name of the dimension whose detail panel is open.
  const [drillDown, setDrillDown] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .get('/profile/executive-summary')
      .then(({ data }) => { if (!cancelled) setData(data); })
      .catch((e) => { if (!cancelled) setErr(e?.response?.data?.detail || 'Failed to compute executive summary'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  if (loading) return <LinearProgress />;
  if (err) return <Alert severity="error">{err}</Alert>;
  if (!data) return null;

  // Drill-down view — render the dimension-specific detail with a breadcrumb
  // back to the summary. This replaces the old "one tab per dimension" UX.
  if (drillDown && DIMENSION_DETAILS[drillDown]) {
    const DetailView = DIMENSION_DETAILS[drillDown];
    return (
      <Box>
        <Breadcrumbs separator={<ChevronRightRoundedIcon sx={{ fontSize: 16, color: '#CBD5E1' }} />} sx={{ mb: 2 }}>
          <Link
            component="button"
            onClick={() => setDrillDown(null)}
            underline="hover"
            sx={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 0.5,
              color: '#6A28A8',
              fontWeight: 600,
              fontSize: '0.84rem',
              background: 'none',
              border: 'none',
              p: 0,
              cursor: 'pointer',
            }}
          >
            <ArrowBackRoundedIcon sx={{ fontSize: 18 }} />
            Data Quality Summary
          </Link>
          <Typography sx={{ fontSize: '0.84rem', fontWeight: 700, color: '#1A1A1A' }}>
            {drillDown}
          </Typography>
        </Breadcrumbs>
        <DetailView />
      </Box>
    );
  }

  const overallStyle = ratingStyle(data.overall_rating);

  return (
    <Box>
      {/* Headline overall-score banner */}
      <Paper
        variant="outlined"
        sx={{
          p: 2.5,
          mb: 2.5,
          borderColor: overallStyle.border,
          background: `linear-gradient(135deg, ${overallStyle.bg} 0%, #FFFFFF 100%)`,
        }}
      >
        <Stack direction={{ xs: 'column', sm: 'row' }} alignItems={{ xs: 'flex-start', sm: 'center' }} justifyContent="space-between" spacing={1.5}>
          <Box>
            <Typography sx={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#8A8A8A', fontWeight: 700 }}>
              Data Quality Assessment
            </Typography>
            <Typography sx={{ fontFamily: "'Montserrat', sans-serif", fontWeight: 700, fontSize: 22, color: '#1A1A1A' }}>
              Overall data quality is {data.overall_rating?.toLowerCase() || 'pending'}.
            </Typography>
            <Typography sx={{ fontSize: '0.82rem', color: '#475569', mt: 0.5 }}>
              Mean score across enabled dimensions. Each dimension is scored independently below; weakest dimensions surface as P1 remediation actions.
            </Typography>
          </Box>
          <Stack direction="row" alignItems="baseline" spacing={1.25}>
            <Typography
              sx={{
                fontFamily: "'Montserrat', sans-serif",
                fontWeight: 800,
                fontSize: 56,
                lineHeight: 1,
                color: overallStyle.fg,
              }}
            >
              {Math.round((data.overall_score || 0) * 100)}
            </Typography>
            <Typography sx={{ fontSize: 18, fontWeight: 700, color: overallStyle.fg }}>/ 100</Typography>
          </Stack>
        </Stack>
      </Paper>

      {/* Dimension scorecard grid */}
      <Typography sx={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#6A28A8', fontWeight: 700, mb: 1.25 }}>
        Dimension Scorecard
      </Typography>
      <Grid container spacing={1.5} sx={{ mb: 3 }}>
        {(data.dimensions || []).map((dim) => (
          <Grid item xs={12} sm={6} md={4} key={dim.dimension}>
            <ScoreCard dim={dim} onDrillDown={setDrillDown} />
          </Grid>
        ))}
      </Grid>

      {/* Two-column footer: Key Statistics + Top Remediation Actions */}
      <Grid container spacing={2.5}>
        <Grid item xs={12} md={5}>
          <Typography sx={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#6A28A8', fontWeight: 700, mb: 1.25 }}>
            Key Statistics
          </Typography>
          <Paper variant="outlined" sx={{ p: 0, maxHeight: 360, overflow: 'auto' }}>
            <Table size="small" stickyHeader>
              <TableBody>
                {(data.key_statistics || []).map((s) => (
                  <TableRow key={s.label} sx={{ '&:last-child td': { borderBottom: 0 } }}>
                    <TableCell sx={{ color: '#475569', fontSize: '0.84rem' }}>{s.label}</TableCell>
                    <TableCell align="right" sx={{ fontWeight: 700, fontVariantNumeric: 'tabular-nums', fontSize: '0.86rem' }}>
                      {s.value}
                    </TableCell>
                  </TableRow>
                ))}
                {(data.key_statistics || []).length === 0 && (
                  <TableRow>
                    <TableCell colSpan={2} sx={{ color: '#8A8A8A', textAlign: 'center', py: 2 }}>
                      No statistics computed yet.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Paper>
        </Grid>

        <Grid item xs={12} md={7}>
          <Typography sx={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#6A28A8', fontWeight: 700, mb: 1.25 }}>
            Top Remediation Actions
          </Typography>
          <Paper variant="outlined" sx={{ p: 0, maxHeight: 360, overflow: 'auto' }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 700, fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A', width: 50 }}>
                    Priority
                  </TableCell>
                  <TableCell sx={{ fontWeight: 700, fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A', width: 140 }}>
                    Dimension
                  </TableCell>
                  <TableCell sx={{ fontWeight: 700, fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A' }}>
                    Action
                  </TableCell>
                  <TableCell sx={{ fontWeight: 700, fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8A8A8A' }}>
                    Estimated impact
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {(data.remediation_actions || []).map((a, i) => {
                  const pri = PRIORITY_STYLE[a.priority] || PRIORITY_STYLE.P3;
                  return (
                    <TableRow key={`${a.priority}-${i}`} sx={{ '&:last-child td': { borderBottom: 0 } }}>
                      <TableCell>
                        <Chip
                          size="small"
                          label={a.priority}
                          sx={{
                            height: 22,
                            fontSize: '0.7rem',
                            fontWeight: 700,
                            color: pri.fg,
                            bgcolor: pri.bg,
                            border: 'none',
                          }}
                        />
                      </TableCell>
                      <TableCell sx={{ fontWeight: 600, fontSize: '0.84rem' }}>{a.dimension}</TableCell>
                      <TableCell sx={{ fontSize: '0.82rem', color: '#1A1A1A' }}>{a.action}</TableCell>
                      <TableCell sx={{ fontSize: '0.78rem', color: '#475569' }}>{a.estimated_records}</TableCell>
                    </TableRow>
                  );
                })}
                {(data.remediation_actions || []).length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4} sx={{ color: '#8A8A8A', textAlign: 'center', py: 2 }}>
                      No remediation actions yet — all dimensions look healthy.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Paper>
        </Grid>
      </Grid>

      {data.warning && (
        <Alert severity="warning" sx={{ mt: 2 }}>
          {data.warning}
        </Alert>
      )}
    </Box>
  );
}
