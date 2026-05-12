import { Box, Typography } from '@mui/material';

/**
 * Compact, design-system stat card. Pass `accent` to highlight a hero
 * metric (purple-tinted background and value). `deltaTone` is one of
 * 'up' | 'down' | undefined to color the optional delta line.
 */
export default function StatCard({ label, value, delta, deltaTone, accent }) {
  const bg = accent ? '#F4ECF9' : '#FBFAFC';
  const border = accent ? 'transparent' : '#E7E6E6';
  const labelColor = accent ? '#6A28A8' : '#8A8A8A';
  const valueColor = accent ? '#6A28A8' : '#1A1A1A';
  const deltaColor =
    deltaTone === 'up' ? '#2F8F57'
    : deltaTone === 'down' ? '#D14343'
    : '#8A8A8A';

  return (
    <Box
      sx={{
        bgcolor: bg,
        border: '1px solid',
        borderColor: border,
        borderRadius: 1.5,
        px: 2.25,
        py: 2,
        minHeight: 86,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
      }}
    >
      <Typography
        sx={{
          fontFamily: "'Open Sans', sans-serif",
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: '0.1em',
          color: labelColor,
          textTransform: 'uppercase',
          mb: 0.75,
        }}
      >
        {label}
      </Typography>
      <Typography
        sx={{
          fontFamily: "'Montserrat', sans-serif",
          fontSize: 26,
          fontWeight: 700,
          lineHeight: 1,
          color: valueColor,
        }}
      >
        {value}
      </Typography>
      {delta && (
        <Typography sx={{ fontSize: 12, color: deltaColor, mt: 0.75 }}>
          {delta}
        </Typography>
      )}
    </Box>
  );
}
