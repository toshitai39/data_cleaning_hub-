import { Paper, Stack, Typography, Box } from '@mui/material';

export default function StatCard({ icon, label, value, hint, accent = 'primary.main' }) {
  return (
    <Paper sx={{ p: 2.5, height: '100%' }}>
      <Stack direction="row" alignItems="center" spacing={1.5} mb={1.5}>
        {icon && (
          <Box
            sx={{
              width: 36,
              height: 36,
              borderRadius: 2,
              background: 'linear-gradient(135deg, #5B1A78 0%, #C81880 100%)',
              color: 'white',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            {icon}
          </Box>
        )}
        <Typography variant="overline" color="text.secondary">{label}</Typography>
      </Stack>
      <Typography variant="h4" sx={{ color: accent, fontWeight: 700 }}>{value}</Typography>
      {hint && (
        <Typography variant="caption" color="text.secondary">{hint}</Typography>
      )}
    </Paper>
  );
}
