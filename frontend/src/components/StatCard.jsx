import { Box, Typography } from '@mui/material';

/**
 * Compact, design-system stat card. Pass `accent` to highlight a hero
 * metric (purple-tinted background and value). `deltaTone` is one of
 * 'up' | 'down' | undefined to color the optional delta line. `dense`
 * tightens padding / fonts so the KpiBar can fit 9 cards across a
 * single row without label wrapping (used on Data Profiling).
 */
export default function StatCard({ label, value, delta, deltaTone, accent, dense = false }) {
  const bg = accent ? '#F4ECF9' : '#FBFAFC';
  const border = accent ? 'transparent' : '#E7E6E6';
  const labelColor = accent ? '#6A28A8' : '#8A8A8A';
  const valueColor = accent ? '#6A28A8' : '#1A1A1A';
  const deltaColor =
    deltaTone === 'up' ? '#2F8F57'
    : deltaTone === 'down' ? '#D14343'
    : '#8A8A8A';

  // Dense mode shaves vertical space + label size so single-word
  // dimension names (COMPLETENESS, STANDARDISATION) fit on one line
  // even when the card sits in a 1.33 / 12 grid column.
  const padX = dense ? 1.5 : 2.25;
  const padY = dense ? 1.25 : 2;
  const minH = dense ? 70 : 86;
  const labelSize = dense ? 9.5 : 11;
  const labelLetterSpacing = dense ? '0.04em' : '0.08em';
  const labelMb = dense ? 0.4 : 0.75;
  const valueSize = dense ? 22 : 26;

  return (
    <Box
      sx={{
        bgcolor: bg,
        border: '1px solid',
        borderColor: border,
        borderRadius: 1.5,
        px: padX,
        py: padY,
        minHeight: minH,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
      }}
    >
      <Typography
        sx={{
          fontFamily: "'Open Sans', sans-serif",
          fontSize: labelSize,
          fontWeight: 700,
          letterSpacing: labelLetterSpacing,
          lineHeight: 1.15,
          color: labelColor,
          textTransform: 'uppercase',
          mb: labelMb,
          // Natural word-boundary wrap only — never split a single word
          // mid-character. The KpiBar dense mode is sized so the longest
          // single-word label (STANDARDISATION) fits on one line at md+.
          overflowWrap: 'break-word',
          hyphens: 'none',
        }}
      >
        {label}
      </Typography>
      <Typography
        sx={{
          fontFamily: "'Montserrat', sans-serif",
          fontSize: valueSize,
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
