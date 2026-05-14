import { Grid } from '@mui/material';
import StatCard from '../../components/StatCard.jsx';

// Order matches the Executive Summary scorecard so visual reading is
// consistent across the page.
const DIMENSION_ORDER = [
  'Completeness',
  'Validation',
  'Uniqueness',
  'Standardisation',
  'Accuracy',
  'Timeliness',
];


export default function KpiBar({ kpi, executiveSummary }) {
  if (!kpi) return null;

  // Look up dimension scores by name so we render them in a fixed
  // canonical order regardless of the backend response order.
  const byDim = {};
  for (const d of (executiveSummary?.dimensions || [])) {
    byDim[d.dimension] = d;
  }

  // Single row of equal-width cards — dataset basics + overall + the six
  // dimension scores. 9 cards on a 12-col grid, every card the same size.
  // Earlier two-row layout looked unbalanced (top row's wider cards made
  // them feel disproportionately important).
  const cells = [
    { label: 'Rows', value: kpi.rows.toLocaleString(), accent: true },
    { label: 'CDEs', value: kpi.columns },
  ];
  if (executiveSummary && typeof executiveSummary.overall_score === 'number') {
    cells.push({
      label: 'Overall',
      value: `${Math.round(executiveSummary.overall_score * 100)}%`,
      accent: true,
    });
  }
  for (const name of DIMENSION_ORDER) {
    const d = byDim[name];
    if (!d) continue;
    cells.push({
      label: name,
      value: d.enabled ? `${Math.round((d.score || 0) * 100)}%` : '—',
    });
  }

  // At md+ all 9 cards sit in one row (12 / 9 ≈ 1.33 cols each). Below
  // md we wrap to 3-per-row at sm and 2-per-row at xs. Compact size
  // pairs with the smaller dense label style on StatCard so every
  // dimension name fits on a single line.
  return (
    <Grid container spacing={1} sx={{ mb: 2.5 }}>
      {cells.map((c) => (
        <Grid item xs={6} sm={4} md={1.33} key={c.label}>
          <StatCard label={c.label} value={c.value} accent={c.accent} dense />
        </Grid>
      ))}
    </Grid>
  );
}
