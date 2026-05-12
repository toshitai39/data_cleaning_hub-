import { Box, Typography } from '@mui/material';

/**
 * Section heading used inside content cards — small accent-colored icon
 * + Montserrat 700 title. Drop in above tables, panels, lists.
 */
export default function SectionTitle({ icon: Icon, children, sx = {} }) {
  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1,
        mb: 1.5,
        mt: 1,
        ...sx,
      }}
    >
      {Icon && <Icon sx={{ fontSize: 18, color: '#6A28A8' }} />}
      <Typography
        sx={{
          fontFamily: "'Montserrat', sans-serif",
          fontSize: 16,
          fontWeight: 700,
          color: '#1A1A1A',
        }}
      >
        {children}
      </Typography>
    </Box>
  );
}
