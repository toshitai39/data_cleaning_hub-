import { useEffect, useMemo, useState } from 'react';
import {
  Box, Grid, Paper, Typography, Alert, LinearProgress, Stack, Chip, Tooltip,
  Table, TableHead, TableBody, TableRow, TableCell, TableContainer,
  TextField, InputAdornment, ToggleButtonGroup, ToggleButton,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import api from '../api.js';
import EmptyState from '../components/EmptyState.jsx';
import PageHeader from '../components/PageHeader.jsx';
import { useDataset } from '../context/DatasetContext.jsx';
import PlotlyChart from './profiling/PlotlyChart.jsx';

// ─── Visual tokens ─────────────────────────────────────────────────
// Refined palette — emerald / topaz / rose instead of fire-engine
// primaries. Reads closer to Linear / Stripe than to a Plotly default.
const TONE = {
  high:     { fg: '#04603A', bg: '#E1F6EB', stroke: '#059669', soft: '#A7F3D0' },
  medium:   { fg: '#7A3E07', bg: '#FEF1DC', stroke: '#C2410C', soft: '#FED7AA' },
  low:      { fg: '#8A1538', bg: '#FCE7EE', stroke: '#E11D48', soft: '#FECDD3' },
  unscored: { fg: '#475569', bg: '#F1F5F9', stroke: '#94A3B8', soft: '#E2E8F0' },
};

// Per-dimension brand colour — used everywhere a dimension is rendered
// so the eye connects the gauge, the chart bar, and the table chip.
const DIM_COLOR = {
  'Completeness':           '#6366F1',
  'Validation':             '#10B981',
  'Uniqueness':             '#06B6D4',
  'Standardisation':        '#F59E0B',
  'Accuracy':               '#8B5CF6',
  'Timeliness':             '#EC4899',
  'Cross-field Validation': '#EF4444',
};

const PLOTLY_CONFIG = { displayModeBar: false, responsive: true };


function toneForScore(pct) {
  if (pct >= 95) return TONE.high;
  if (pct >= 70) return TONE.medium;
  return TONE.low;
}


// ─── Hero KPI card ────────────────────────────────────────────────
// Two flavours: solid (default), gradient (accent). Subtle drop-shadow,
// generous numeric typography, supporting line in the same colour family
// as the value.

function HeroCard({ label, value, sub, accent, color }) {
  const bg = accent
    ? 'linear-gradient(135deg, #4A1F77 0%, #7B2D9B 50%, #B11D77 100%)'
    : '#FFFFFF';
  return (
    <Paper
      elevation={0}
      sx={{
        position: 'relative',
        overflow: 'hidden',
        px: 2.25, py: 1.75,
        height: '100%',
        borderRadius: 2.5,
        background: bg,
        color: accent ? '#FFFFFF' : '#1A1A1A',
        border: accent ? 'none' : '1px solid #ECE7F2',
        boxShadow: accent
          ? '0 12px 30px -8px rgba(73,32,121,0.45)'
          : '0 1px 2px rgba(15,15,30,0.05), 0 8px 24px -16px rgba(15,15,30,0.08)',
        transition: 'transform 200ms ease, box-shadow 200ms ease',
        '&:hover': {
          transform: accent ? 'translateY(-1px)' : 'none',
          boxShadow: accent
            ? '0 16px 36px -8px rgba(73,32,121,0.55)'
            : '0 1px 2px rgba(15,15,30,0.05), 0 12px 32px -16px rgba(15,15,30,0.12)',
        },
      }}
    >
      {/* Soft brand-coloured accent stripe on non-accent cards */}
      {!accent && color && (
        <Box sx={{
          position: 'absolute', top: 0, left: 0, height: '100%', width: 3,
          background: color,
        }} />
      )}
      <Typography sx={{
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: '0.07em',
        textTransform: 'uppercase',
        color: accent ? 'rgba(255,255,255,0.78)' : '#7C7892',
        mb: 0.75,
      }}>
        {label}
      </Typography>
      <Typography sx={{
        fontFamily: "'Montserrat', sans-serif",
        fontWeight: 800,
        fontSize: 30,
        lineHeight: 1,
        letterSpacing: '-0.015em',
      }}>
        {value}
      </Typography>
      {sub && (
        <Typography sx={{
          fontSize: 12.5,
          mt: 0.75,
          color: accent ? 'rgba(255,255,255,0.85)' : '#6B6781',
        }}>
          {sub}
        </Typography>
      )}
    </Paper>
  );
}


// ─── Speedometer gauge ────────────────────────────────────────────
// Proper half-circle speedometer SVG. Three faint background zones (red /
// amber / green for 0-70 / 70-95 / 95-100), an active arc that fills
// from 0° to the value angle in a colour matching the active zone,
// and a value + "/ 100" readout inside the dial.

function SpeedometerGauge({ value, size = 200, gradientId }) {
  const W = size;
  const H = size * 0.62;
  const cx = W / 2;
  const cy = H * 0.92;
  const r  = W * 0.40;
  const sw = W * 0.07;

  const clamped = Math.max(0, Math.min(100, value || 0));
  const polar = (radius, angleDeg) => {
    const rad = (angleDeg - 180) * (Math.PI / 180);
    return { x: cx + radius * Math.cos(rad), y: cy + radius * Math.sin(rad) };
  };
  const arcPath = (radius, fromDeg, toDeg) => {
    const start = polar(radius, fromDeg);
    const end   = polar(radius, toDeg);
    const large = toDeg - fromDeg > 180 ? 1 : 0;
    return `M ${start.x} ${start.y} A ${radius} ${radius} 0 ${large} 1 ${end.x} ${end.y}`;
  };
  const pctToDeg = (p) => (p / 100) * 180;

  const tone = clamped >= 95 ? TONE.high : clamped >= 70 ? TONE.medium : TONE.low;
  const gid = `gauge-grad-${gradientId || Math.round(clamped)}`;

  return (
    <Box sx={{ width: W, height: H + 4, mx: 'auto', position: 'relative' }}>
      <svg width={W} height={H + 4} viewBox={`0 0 ${W} ${H + 4}`}>
        <defs>
          {/* Soft gradient along the active arc — more refined than a
              single flat colour. Lighter near 0%, deeper near the value. */}
          <linearGradient id={gid} x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%"   stopColor={tone.soft} />
            <stop offset="100%" stopColor={tone.stroke} />
          </linearGradient>
        </defs>

        {/* Track — full 0→100 arc in a very light neutral */}
        <path
          d={arcPath(r, 0, 180)}
          stroke="#EFEAF7" strokeWidth={sw} fill="none" strokeLinecap="round"
        />
        {/* Active arc — gradient, value-coloured */}
        {clamped > 0 && (
          <path
            d={arcPath(r, 0, pctToDeg(clamped))}
            stroke={`url(#${gid})`} strokeWidth={sw} fill="none" strokeLinecap="round"
            style={{ transition: 'd 700ms cubic-bezier(0.22, 1, 0.36, 1)' }}
          />
        )}

        {/* Big value number inside the dial */}
        <text
          x={cx} y={cy - 14}
          textAnchor="middle"
          style={{
            fontFamily: "Montserrat, sans-serif",
            fontWeight: 800,
            fontSize: W >= 180 ? 42 : 32,
            fill: '#1A1A1A',
            letterSpacing: '-0.025em',
          }}
        >
          {Math.round(clamped)}
        </text>
        {/* Out-of-100 subscript */}
        <text
          x={cx} y={cy + 4}
          textAnchor="middle"
          style={{
            fontFamily: "'Open Sans', sans-serif",
            fontSize: 9,
            fontWeight: 700,
            letterSpacing: '0.18em',
            fill: '#9994A6',
          }}
        >
          OUT OF 100
        </text>
      </svg>
    </Box>
  );
}

// Small inline ring used by the Overall pill at the panel header.
function MiniRing({ value, color, size = 56, stroke = 6 }) {
  const radius = (size - stroke) / 2;
  const c = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(100, value));
  const offset = c - (clamped / 100) * c;
  return (
    <Box sx={{ position: 'relative', width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size/2} cy={size/2} r={radius} stroke="#EFEAF7" strokeWidth={stroke} fill="none" />
        <circle cx={size/2} cy={size/2} r={radius} stroke={color} strokeWidth={stroke} fill="none"
                strokeDasharray={c} strokeDashoffset={offset} strokeLinecap="round" />
      </svg>
      <Box sx={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <Typography sx={{ fontFamily: "'Montserrat', sans-serif", fontWeight: 800, fontSize: 16, color: '#1A1A1A', lineHeight: 1 }}>
          {Math.round(clamped)}
        </Typography>
        <Typography sx={{ fontSize: 8, color: '#9994A6', fontWeight: 700, letterSpacing: '0.1em' }}>%</Typography>
      </Box>
    </Box>
  );
}


// ─── Dimension scorecard ──────────────────────────────────────────
// One panel containing six rows, each: ring + dimension name + rating
// chip + progress bar. Replaces the prior six-individual-card layout —
// much less empty space and visually unified.

function DimensionScorecard({ dimensions, overallScore }) {
  return (
    <Paper
      elevation={0}
      sx={{
        p: 2.5,
        borderRadius: 2.5,
        bgcolor: '#FFFFFF',
        border: '1px solid #ECE7F2',
        boxShadow: '0 1px 2px rgba(15,15,30,0.05), 0 12px 32px -20px rgba(15,15,30,0.08)',
      }}
    >
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Box>
          <Typography sx={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#6A28A8' }}>
            Dimension scorecard
          </Typography>
          <Typography sx={{ fontSize: 12.5, color: '#7C7892', mt: 0.25 }}>
            Six quality dimensions, each scored out of 100 against your dataset.
          </Typography>
        </Box>
        {typeof overallScore === 'number' && (
          <Stack direction="row" spacing={1.5} alignItems="center" sx={{ pr: 0.5 }}>
            <Box>
              <Typography sx={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#7C7892', textAlign: 'right' }}>
                Overall
              </Typography>
              <Typography sx={{ fontSize: 10, color: '#9994A6', textAlign: 'right' }}>
                {toneForScore(overallScore * 100).fg && (toneForScore(overallScore * 100) === TONE.high ? 'Strong' :
                  toneForScore(overallScore * 100) === TONE.medium ? 'Moderate' : 'Needs attention')}
              </Typography>
            </Box>
            <MiniRing value={overallScore * 100} color={toneForScore(overallScore * 100).stroke} size={56} stroke={6} />
          </Stack>
        )}
      </Stack>
      <Grid container spacing={2}>
        {(dimensions || []).map((d) => {
          const enabled = d.enabled && typeof d.score === 'number';
          const pct = enabled ? d.score * 100 : 0;
          const tone = enabled ? toneForScore(pct) : TONE.unscored;
          const accent = DIM_COLOR[d.dimension] || tone.stroke;
          return (
            <Grid item xs={12} sm={6} md={4} key={d.dimension}>
              <Box
                sx={{
                  position: 'relative',
                  px: 2, py: 1.75,
                  height: '100%',
                  borderRadius: 2,
                  bgcolor: '#FBFAFC',
                  border: '1px solid #F2EEF8',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  textAlign: 'center',
                  transition: 'all 180ms ease',
                  '&:hover': {
                    bgcolor: '#FFFFFF',
                    borderColor: accent,
                    boxShadow: `0 0 0 1px ${accent}22, 0 10px 22px -12px ${accent}66`,
                    transform: 'translateY(-1px)',
                  },
                }}
              >
                {/* Dimension name + brand-colour pill */}
                <Stack direction="row" alignItems="center" spacing={0.875} sx={{ mb: 0.75 }}>
                  <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: accent }} />
                  <Typography sx={{
                    fontSize: 11.5,
                    fontWeight: 700,
                    letterSpacing: '0.08em',
                    textTransform: 'uppercase',
                    color: '#1A1A1A',
                  }}>
                    {d.dimension}
                  </Typography>
                </Stack>

                {/* The actual speedometer */}
                {enabled ? (
                  <SpeedometerGauge value={pct} accent={accent} size={180} />
                ) : (
                  <Box sx={{ height: 130, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                    <Typography sx={{ fontFamily: "'Montserrat', sans-serif", fontWeight: 800, fontSize: 28, color: '#CBD5E1' }}>—</Typography>
                    <Typography sx={{ fontSize: 11, color: '#9994A6', mt: 0.5 }}>Not yet measurable</Typography>
                  </Box>
                )}

                {/* Rating + risk underneath */}
                <Stack direction="row" spacing={0.75} alignItems="center" justifyContent="center" sx={{ mt: 0.75 }}>
                  <Chip
                    size="small"
                    label={enabled ? d.rating : 'N/A'}
                    sx={{
                      height: 20, fontSize: 10.5, fontWeight: 700,
                      color: tone.fg, bgcolor: tone.bg, border: 'none',
                      '& .MuiChip-label': { px: 0.875 },
                    }}
                  />
                  {enabled && (
                    <Typography sx={{ fontSize: 11.5, color: '#7C7892' }}>
                      · Risk <Box component="span" sx={{ color: '#1A1A1A', fontWeight: 600 }}>{d.risk_level}</Box>
                    </Typography>
                  )}
                </Stack>
              </Box>
            </Grid>
          );
        })}
      </Grid>
    </Paper>
  );
}


// ─── CDE health donut ─────────────────────────────────────────────
// A proper polished donut. Big in the centre, legend right.

const DONUT_PALETTE = {
  High:     '#059669',   // emerald
  Medium:   '#C2410C',   // burnt orange
  Low:      '#E11D48',   // rose
  Unscored: '#94A3B8',   // slate
};

function CDEHealthDonut({ counts, total }) {
  const order = ['High', 'Medium', 'Low', 'Unscored'];
  const entries = order
    .map((k) => ({ k, v: counts[k] || 0 }))
    .filter((e) => e.v > 0);

  if (entries.length === 0 || !total) {
    return (
      <Typography sx={{ fontSize: 13, color: '#7C7892', textAlign: 'center', py: 4 }}>
        No CDEs scored yet.
      </Typography>
    );
  }

  const data = [{
    type: 'pie',
    hole: 0.74,
    values: entries.map((e) => e.v),
    labels: entries.map((e) => e.k),
    marker: {
      colors: entries.map((e) => DONUT_PALETTE[e.k]),
      line: { color: '#FFFFFF', width: 4 },
    },
    textinfo: 'none',
    hovertemplate: '<b>%{label}</b>  ·  %{value} CDEs  (%{percent})<extra></extra>',
    sort: false,
    direction: 'clockwise',
    rotation: 90,
  }];

  const high = counts.High || 0;
  const healthyPct = total ? Math.round((high / total) * 100) : 0;

  const layout = {
    height: 220,
    margin: { l: 8, r: 8, t: 8, b: 8 },
    showlegend: false,
    paper_bgcolor: 'rgba(0,0,0,0)',
    annotations: [
      {
        text: `<span style="font-family:Montserrat,sans-serif;font-size:30px;font-weight:800;color:#1A1A1A;letter-spacing:-0.02em">${healthyPct}%</span><br><span style="font-size:9px;color:#9994A6;font-weight:700;letter-spacing:0.18em">HEALTHY</span>`,
        x: 0.5, y: 0.5, showarrow: false,
      },
    ],
  };

  return (
    <Box>
      <PlotlyChart data={data} layout={layout} config={PLOTLY_CONFIG} />
      <Stack direction="row" spacing={2} justifyContent="center" flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
        {entries.map((e) => (
          <Stack key={e.k} direction="row" spacing={0.875} alignItems="center">
            <Box sx={{
              width: 10, height: 10, borderRadius: '50%',
              bgcolor: DONUT_PALETTE[e.k],
              boxShadow: `0 0 0 2px ${DONUT_PALETTE[e.k]}1A`,
            }} />
            <Typography sx={{ fontSize: 12, color: '#1A1A1A', fontWeight: 600 }}>
              {e.k}
              <Box component="span" sx={{ color: '#9994A6', fontWeight: 500, ml: 0.5, fontFamily: 'Montserrat, sans-serif' }}>
                {e.v}
              </Box>
            </Typography>
          </Stack>
        ))}
      </Stack>
    </Box>
  );
}


// ─── Per-dimension distribution — refined SVG proportion bars ─────
// Each row: dimension label, a thin horizontal bar split into High /
// Medium / Low segments by proportion, with the applicable-CDE count
// on the right. Far cleaner than the prior Plotly stack — no axes, no
// gridlines, no legend at the bottom; just type, ratio, and number.

function DimensionDistributionChart({ buckets }) {
  if (!buckets || buckets.length === 0) {
    return (
      <Typography sx={{ fontSize: 13, color: '#7C7892', textAlign: 'center', py: 4 }}>
        No dimension data yet.
      </Typography>
    );
  }
  return (
    <Box>
      <Stack spacing={1.25}>
        {buckets.map((b) => {
          const high   = b.buckets.High   || 0;
          const medium = b.buckets.Medium || 0;
          const low    = b.buckets.Low    || 0;
          const total  = high + medium + low;
          const pct = (n) => (total ? (n / total) * 100 : 0);
          return (
            <Box key={b.dimension}>
              <Stack direction="row" justifyContent="space-between" alignItems="baseline" sx={{ mb: 0.4 }}>
                <Typography sx={{ fontSize: 12, fontWeight: 600, color: '#1A1A1A' }}>
                  {b.dimension}
                </Typography>
                <Stack direction="row" spacing={1} alignItems="baseline">
                  {total === 0 ? (
                    <Typography sx={{ fontSize: 10.5, color: '#CBD5E1', fontStyle: 'italic' }}>
                      not measurable
                    </Typography>
                  ) : (
                    <>
                      {high   > 0 && <Typography sx={{ fontSize: 10.5, color: DONUT_PALETTE.High,   fontWeight: 700 }}>{high}</Typography>}
                      {medium > 0 && <Typography sx={{ fontSize: 10.5, color: DONUT_PALETTE.Medium, fontWeight: 700 }}>{medium}</Typography>}
                      {low    > 0 && <Typography sx={{ fontSize: 10.5, color: DONUT_PALETTE.Low,    fontWeight: 700 }}>{low}</Typography>}
                      <Typography sx={{ fontFamily: "'Montserrat', sans-serif", fontWeight: 700, fontSize: 12, color: '#1A1A1A' }}>
                        {total}
                      </Typography>
                    </>
                  )}
                </Stack>
              </Stack>
              <Box sx={{
                display: 'flex',
                height: 8,
                borderRadius: 99,
                overflow: 'hidden',
                bgcolor: total === 0 ? '#F1F5F9' : '#F4ECF9',
              }}>
                {total > 0 && (
                  <>
                    {high > 0 && (
                      <Tooltip title={`High · ${high}`} arrow>
                        <Box sx={{
                          width: `${pct(high)}%`,
                          background: `linear-gradient(90deg, ${DONUT_PALETTE.High}CC 0%, ${DONUT_PALETTE.High} 100%)`,
                          transition: 'width 600ms cubic-bezier(0.22, 1, 0.36, 1)',
                        }} />
                      </Tooltip>
                    )}
                    {medium > 0 && (
                      <Tooltip title={`Medium · ${medium}`} arrow>
                        <Box sx={{
                          width: `${pct(medium)}%`,
                          background: `linear-gradient(90deg, ${DONUT_PALETTE.Medium}CC 0%, ${DONUT_PALETTE.Medium} 100%)`,
                          transition: 'width 600ms cubic-bezier(0.22, 1, 0.36, 1)',
                        }} />
                      </Tooltip>
                    )}
                    {low > 0 && (
                      <Tooltip title={`Low · ${low}`} arrow>
                        <Box sx={{
                          width: `${pct(low)}%`,
                          background: `linear-gradient(90deg, ${DONUT_PALETTE.Low}CC 0%, ${DONUT_PALETTE.Low} 100%)`,
                          transition: 'width 600ms cubic-bezier(0.22, 1, 0.36, 1)',
                        }} />
                      </Tooltip>
                    )}
                  </>
                )}
              </Box>
            </Box>
          );
        })}
      </Stack>
      {/* Legend — three small chips, mirrored from the donut */}
      <Stack direction="row" spacing={2} justifyContent="center" sx={{ mt: 2, pt: 1.5, borderTop: '1px dashed #ECE7F2' }}>
        {['High', 'Medium', 'Low'].map((k) => (
          <Stack key={k} direction="row" spacing={0.75} alignItems="center">
            <Box sx={{
              width: 8, height: 8, borderRadius: '50%',
              bgcolor: DONUT_PALETTE[k],
              boxShadow: `0 0 0 2px ${DONUT_PALETTE[k]}1A`,
            }} />
            <Typography sx={{ fontSize: 11, color: '#7C7892', fontWeight: 600 }}>{k}</Typography>
          </Stack>
        ))}
      </Stack>
    </Box>
  );
}


// ─── Rules-by-dimension horizontal-bar list ───────────────────────

function RulesByDimensionList({ data: rules }) {
  if (!rules || rules.length === 0) {
    return (
      <Stack alignItems="center" justifyContent="center" sx={{ py: 4 }} spacing={0.75}>
        <Box sx={{
          width: 36, height: 36, borderRadius: '50%',
          bgcolor: '#F4ECF9', color: '#6A28A8',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 18,
        }}>
          ⚙
        </Box>
        <Typography sx={{ fontSize: 13, fontWeight: 600, color: '#1A1A1A' }}>
          No rules generated yet
        </Typography>
        <Typography sx={{ fontSize: 12, color: '#7C7892', textAlign: 'center', maxWidth: 220 }}>
          Run <b>Rule Generator</b> to populate this view with per-dimension rule counts.
        </Typography>
      </Stack>
    );
  }
  const total = rules.reduce((acc, r) => acc + (r.rule_count || 0), 0) || 1;
  return (
    <Stack spacing={1.25}>
      {rules.map((r) => {
        const pct = (r.rule_count / total) * 100;
        const color = DIM_COLOR[r.dimension] || '#94A3B8';
        return (
          <Box key={r.dimension}>
            <Stack direction="row" justifyContent="space-between" alignItems="baseline" sx={{ mb: 0.4 }}>
              <Typography sx={{ fontSize: 12.5, fontWeight: 600, color: '#1A1A1A' }}>
                {r.dimension}
              </Typography>
              <Stack direction="row" spacing={0.75} alignItems="baseline">
                <Typography sx={{ fontFamily: "'Montserrat', sans-serif", fontWeight: 700, fontSize: 14, color: '#1A1A1A' }}>
                  {r.rule_count}
                </Typography>
                <Typography sx={{ fontSize: 10.5, color: '#9994A6', fontWeight: 600 }}>
                  {pct.toFixed(0)}%
                </Typography>
              </Stack>
            </Stack>
            <Box sx={{ height: 6, borderRadius: 99, bgcolor: '#F0EBF7', overflow: 'hidden' }}>
              <Box sx={{
                width: `${pct}%`, height: '100%', borderRadius: 99,
                background: `linear-gradient(90deg, ${color}AA 0%, ${color} 100%)`,
                transition: 'width 600ms cubic-bezier(0.22, 1, 0.36, 1)',
              }} />
            </Box>
          </Box>
        );
      })}
    </Stack>
  );
}


// ─── Panel chrome ─────────────────────────────────────────────────

function Panel({ title, subtitle, children, action }) {
  return (
    <Paper
      elevation={0}
      sx={{
        p: 2.25,
        height: '100%',
        borderRadius: 2.5,
        bgcolor: '#FFFFFF',
        border: '1px solid #ECE7F2',
        boxShadow: '0 1px 2px rgba(15,15,30,0.05), 0 12px 32px -20px rgba(15,15,30,0.08)',
      }}
    >
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 1.25 }}>
        <Box>
          <Typography sx={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#6A28A8' }}>
            {title}
          </Typography>
          {subtitle && (
            <Typography sx={{ fontSize: 12.5, color: '#7C7892', mt: 0.25 }}>
              {subtitle}
            </Typography>
          )}
        </Box>
        {action}
      </Stack>
      {children}
    </Paper>
  );
}


// ─── Main page ────────────────────────────────────────────────────

export default function Dashboard() {
  const { state } = useDataset();
  const [data, setData] = useState(null);
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [thresholdFilter, setThresholdFilter] = useState('all');

  useEffect(() => {
    if (!state.loaded) return;
    let cancelled = false;
    setLoading(true);
    api
      .get('/profile/quality-dashboard')
      .then(({ data }) => { if (!cancelled) setData(data); })
      .catch((e) => { if (!cancelled) setErr(e?.response?.data?.detail || 'Dashboard load failed'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [state.loaded, state.operations]);

  const fieldsView = useMemo(() => {
    const fields = data?.per_field || [];
    let base = fields;
    if (thresholdFilter !== 'all') {
      base = base.filter((f) => f.threshold.toLowerCase() === thresholdFilter);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      base = base.filter((f) =>
        f.field.toLowerCase().includes(q) ||
        (f.semantic_type || '').toLowerCase().includes(q),
      );
    }
    return base;
  }, [data, search, thresholdFilter]);

  if (!state.loaded) {
    return (
      <>
        <PageHeader title="Data Quality Dashboard" subtitle="Cross-dimensional executive view of your critical data elements." />
        <EmptyState />
      </>
    );
  }
  if (loading && !data) return <LinearProgress />;
  if (err) return <Alert severity="error">{err}</Alert>;
  if (!data) return null;

  const s = data.summary || {};
  const totalForThreshold = Object.values(data.threshold_distribution || {}).reduce((a, b) => a + b, 0);

  return (
    <Box sx={{ pb: 4 }}>
      <PageHeader
        title="Data Quality Dashboard"
        subtitle="Executive outlook — fed live from the profiling assessment."
      />

      {/* HERO STRIP */}
      <Grid container spacing={1.5} sx={{ mb: 2 }}>
        <Grid item xs={12} sm={6} md={3}>
          <HeroCard
            label="Critical Data Elements"
            value={s.total_cdes}
            sub={s.recommended_cdes ? `${s.recommended_cdes} flagged as recommended by AI` : 'In scope for this analysis'}
            color="#6366F1"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <HeroCard
            label="Active Records"
            value={(s.total_records || 0).toLocaleString()}
            sub={s.stream_label ? `${s.system_label || ''} · ${s.stream_label}` : 'In current scope'}
            color="#06B6D4"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <HeroCard
            label="Data Quality Rules"
            value={s.total_rules || 0}
            sub={s.total_rules > 0 ? 'Per-dimension + cross-field combined' : 'Run Rule Generator to populate'}
            color="#F59E0B"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <HeroCard
            label="Average Data Quality Score"
            value={`${Math.round((s.overall_score || 0) * 100)}%`}
            sub="Mean of enabled dimensions"
            accent
          />
        </Grid>
      </Grid>

      {/* DIMENSION SCORECARD — one unified panel */}
      <Box sx={{ mb: 2 }}>
        <DimensionScorecard
          dimensions={data.dimension_scores || []}
          overallScore={s.overall_score}
        />
      </Box>

      {/* TWO ANALYTICAL PANELS */}
      <Grid container spacing={1.5} sx={{ mb: 2 }}>
        <Grid item xs={12} md={4}>
          <Panel
            title="CDE Health Distribution"
            subtitle={`Where your ${s.total_cdes} CDEs land on the threshold scale.`}
          >
            <CDEHealthDonut counts={data.threshold_distribution} total={totalForThreshold} />
          </Panel>
        </Grid>
        <Grid item xs={12} md={4}>
          <Panel
            title="CDEs across threshold categories"
            subtitle="High / Medium / Low per dimension."
          >
            <DimensionDistributionChart buckets={data.dimension_threshold_buckets || []} />
          </Panel>
        </Grid>
        <Grid item xs={12} md={4}>
          <Panel
            title="Rules by dimension"
            subtitle={s.total_rules > 0 ? `${s.total_rules} rules in scope.` : 'Run Rule Generator to populate.'}
          >
            <RulesByDimensionList data={data.rules_by_dimension || []} />
          </Panel>
        </Grid>
      </Grid>

      {/* CDE-LEVEL TABLE */}
      <Panel
        title={`CDE-level scorecard (${fieldsView.length} of ${(data.per_field || []).length})`}
        subtitle="Per-field per-dimension scoring. Worst-first."
        action={
          <Stack direction="row" spacing={1.25}>
            <TextField
              size="small"
              placeholder="Filter field or type…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon fontSize="small" />
                  </InputAdornment>
                ),
              }}
              sx={{ minWidth: 220 }}
            />
            <ToggleButtonGroup
              value={thresholdFilter}
              exclusive
              size="small"
              onChange={(_, v) => v && setThresholdFilter(v)}
              sx={{
                '& .MuiToggleButton-root': {
                  textTransform: 'none', fontSize: 12, fontWeight: 600,
                  px: 1.5, py: 0.5,
                },
              }}
            >
              <ToggleButton value="all">All</ToggleButton>
              <ToggleButton value="high">High</ToggleButton>
              <ToggleButton value="medium">Medium</ToggleButton>
              <ToggleButton value="low">Low</ToggleButton>
            </ToggleButtonGroup>
          </Stack>
        }
      >
        <TableContainer sx={{ maxHeight: 480, mt: 0.5, borderRadius: 1.5 }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                {[
                  ['Critical Data Element', 'left'],
                  ['Type', 'left'],
                  ['Completeness', 'right'],
                  ['Validation', 'right'],
                  ['Uniqueness', 'right'],
                  ['Standardisation', 'right'],
                  ['Overall', 'right'],
                  ['Non-compliant', 'right'],
                  ['Threshold', 'left'],
                ].map(([h, align]) => (
                  <TableCell
                    key={h}
                    align={align}
                    sx={{
                      fontWeight: 700, fontSize: 10.5, textTransform: 'uppercase',
                      letterSpacing: '0.07em', color: '#7C7892',
                      bgcolor: '#FBFAFC',
                      borderBottom: '1px solid #ECE7F2',
                    }}
                  >
                    {h}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {fieldsView.length === 0 && (
                <TableRow>
                  <TableCell colSpan={9} sx={{ color: '#7C7892', textAlign: 'center', py: 3, fontSize: 13 }}>
                    No fields match your filter.
                  </TableCell>
                </TableRow>
              )}
              {fieldsView.map((f) => {
                const tone = TONE[f.threshold?.toLowerCase()] || TONE.unscored;
                const cell = (v) => v == null
                  ? <Box component="span" sx={{ color: '#CBD5E1' }}>—</Box>
                  : `${(v * 100).toFixed(1)}%`;
                return (
                  <TableRow
                    key={f.field}
                    sx={{ '&:hover': { bgcolor: '#FBFAFC' } }}
                  >
                    <TableCell sx={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace", fontSize: 12.5, fontWeight: 600 }}>{f.field}</TableCell>
                    <TableCell sx={{ color: '#7C7892', fontSize: 12 }}>{f.semantic_type || '—'}</TableCell>
                    <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums', fontSize: 12.5 }}>{cell(f.completeness)}</TableCell>
                    <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums', fontSize: 12.5 }}>{cell(f.validation)}</TableCell>
                    <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums', fontSize: 12.5 }}>{cell(f.uniqueness)}</TableCell>
                    <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums', fontSize: 12.5 }}>{cell(f.standardisation)}</TableCell>
                    <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums', fontSize: 13, fontWeight: 700, color: '#1A1A1A' }}>{cell(f.overall_score)}</TableCell>
                    <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums', fontSize: 12.5, color: f.non_compliant_count > 0 ? '#9F1A1A' : '#9994A6', fontWeight: f.non_compliant_count > 0 ? 700 : 400 }}>
                      {(f.non_compliant_count || 0).toLocaleString()}
                    </TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        label={f.threshold}
                        sx={{
                          height: 20, fontSize: 10.5, fontWeight: 700,
                          color: tone.fg, bgcolor: tone.bg, border: 'none',
                          '& .MuiChip-label': { px: 0.875 },
                        }}
                      />
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      </Panel>
    </Box>
  );
}
