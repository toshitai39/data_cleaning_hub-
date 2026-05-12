import { Button } from '@mui/material';

/**
 * Outlined accent action button matching the reference design.
 * Three tones:
 *   default → white bg, neutral border, accent text, accent-bg on hover
 *   success → soft green
 *   danger  → red text, red border on hover
 */
export default function ActionButton({
  tone = 'default',
  startIcon,
  endIcon,
  children,
  fullWidth = true,
  ...rest
}) {
  const palettes = {
    default: {
      color: '#6A28A8',
      bg: '#FFFFFF',
      border: '#E7E6E6',
      hoverBg: '#F4ECF9',
      hoverBorder: '#6A28A8',
    },
    success: {
      color: '#2F8F57',
      bg: '#E8F4ED',
      border: 'rgba(47,143,87,0.30)',
      hoverBg: '#DCEFE3',
      hoverBorder: 'rgba(47,143,87,0.45)',
    },
    danger: {
      color: '#D14343',
      bg: '#FFFFFF',
      border: '#E7E6E6',
      hoverBg: '#FBEAEA',
      hoverBorder: '#D14343',
    },
  };
  const p = palettes[tone] || palettes.default;

  return (
    <Button
      fullWidth={fullWidth}
      startIcon={startIcon}
      endIcon={endIcon}
      sx={{
        py: 1.25,
        px: 2,
        bgcolor: p.bg,
        color: p.color,
        border: '1px solid',
        borderColor: p.border,
        borderRadius: 1.25,
        fontSize: 13.5,
        fontWeight: 600,
        textTransform: 'none',
        boxShadow: 'none',
        '&:hover': {
          bgcolor: p.hoverBg,
          borderColor: p.hoverBorder,
          boxShadow: 'none',
        },
        '&.Mui-disabled': {
          color: '#8A8A8A',
          bgcolor: '#FBFAFC',
          borderColor: '#E7E6E6',
          opacity: 0.7,
        },
      }}
      {...rest}
    >
      {children}
    </Button>
  );
}
