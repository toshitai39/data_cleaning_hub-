import { Grid, Paper, Typography, Box } from '@mui/material';

const Card = ({ label, value }) => (
  <Paper
    sx={{
      p: 2.25,
      textAlign: 'center',
      borderRadius: 2.5,
      transition: 'transform 0.25s, box-shadow 0.25s',
      '&:hover': { transform: 'translateY(-3px)', boxShadow: '0 4px 12px rgba(0,0,0,0.08)' },
    }}
  >
    <Typography
      variant="caption"
      sx={{ color: 'text.secondary', textTransform: 'uppercase', letterSpacing: 1, fontWeight: 500 }}
    >
      {label}
    </Typography>
    <Typography sx={{ fontSize: '1.6rem', fontWeight: 700, color: 'primary.main', mt: 0.75 }}>
      {value}
    </Typography>
  </Paper>
);

export default function KpiBar({ kpi }) {
  if (!kpi) return null;
  const cells = [
    ['Rows', kpi.rows.toLocaleString()],
    ['Columns', kpi.columns],
    ['Quality', `${kpi.quality_pct.toFixed(0)}%`],
    ['Completeness', `${kpi.completeness_pct.toFixed(1)}%`],
    ['Missing', kpi.missing_cells.toLocaleString()],
    ['Fill Rate', kpi.fill_rate_pct == null ? 'N/A' : `${kpi.fill_rate_pct.toFixed(1)}%`],
  ];
  return (
    <Grid container spacing={1.5} sx={{ mb: 2.5 }}>
      {cells.map(([label, value]) => (
        <Grid item xs={6} sm={4} md={2} key={label}>
          <Card label={label} value={value} />
        </Grid>
      ))}
    </Grid>
  );
}
