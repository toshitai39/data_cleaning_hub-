import { Grid } from '@mui/material';
import StatCard from '../../components/StatCard.jsx';

export default function KpiBar({ kpi }) {
  if (!kpi) return null;
  const cells = [
    { label: 'Rows', value: kpi.rows.toLocaleString(), accent: true },
    { label: 'Critical data elements', value: kpi.columns },
    { label: 'Quality', value: `${kpi.quality_pct.toFixed(0)}%` },
    { label: 'Completeness', value: `${kpi.completeness_pct.toFixed(1)}%` },
    { label: 'Missing', value: kpi.missing_cells.toLocaleString() },
    {
      label: 'Fill rate',
      value: kpi.fill_rate_pct == null ? 'N/A' : `${kpi.fill_rate_pct.toFixed(1)}%`,
    },
  ];
  return (
    <Grid container spacing={1.5} sx={{ mb: 2.5 }}>
      {cells.map((c) => (
        <Grid item xs={6} sm={4} md={2} key={c.label}>
          <StatCard label={c.label} value={c.value} accent={c.accent} />
        </Grid>
      ))}
    </Grid>
  );
}
