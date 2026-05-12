import { Box } from '@mui/material';

/**
 * Single-purpose white panel that hosts a page's main content. Mirrors the
 * Agent Hub reference: 1px border, rounded corners, generous padding,
 * subtle shadow.
 */
export default function ContentCard({ children, sx = {}, padding = true }) {
  return (
    <Box
      sx={{
        bgcolor: '#FFFFFF',
        border: '1px solid #E7E6E6',
        borderRadius: 1.5,
        boxShadow: '0 1px 2px rgba(73,32,121,0.04)',
        p: padding ? { xs: 2.5, md: 4 } : 0,
        ...sx,
      }}
    >
      {children}
    </Box>
  );
}
