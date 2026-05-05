import { createTheme } from '@mui/material/styles';

// Uniqus brand palette — deep purple → magenta gradient with neutral slates.
export const UNIQUS = {
  purpleDeep: '#3D1654',     // primary dark
  purple:     '#5B1A78',     // primary
  magenta:    '#9C1E7A',     // primary light
  pink:       '#C81880',     // accent
  pinkBright: '#E0218A',     // accent bright
  gradient:   'linear-gradient(135deg, #3D1654 0%, #5B1A78 35%, #9C1E7A 70%, #C81880 100%)',
  gradientSoft: 'linear-gradient(135deg, #5B1A78 0%, #C81880 100%)',
};

export const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: UNIQUS.purple, light: UNIQUS.magenta, dark: UNIQUS.purpleDeep, contrastText: '#fff' },
    secondary: { main: UNIQUS.pink, light: UNIQUS.pinkBright, contrastText: '#fff' },
    success: { main: '#10b981' },
    warning: { main: '#f59e0b' },
    error: { main: '#ef4444' },
    background: { default: '#faf7fb', paper: '#ffffff' },
    text: { primary: '#1a0a23', secondary: '#6b5c73' },
    divider: '#ece4ef',
  },
  shape: { borderRadius: 12 },
  typography: {
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    h4: { fontWeight: 700, letterSpacing: '-0.02em' },
    h5: { fontWeight: 700, letterSpacing: '-0.01em' },
    h6: { fontWeight: 600 },
    button: { textTransform: 'none', fontWeight: 600 },
  },
  components: {
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          border: '1px solid #ece4ef',
          boxShadow: '0 1px 3px rgba(61,22,84,0.04), 0 4px 16px rgba(61,22,84,0.04)',
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: { borderRadius: 10 },
        containedPrimary: {
          background: UNIQUS.gradientSoft,
          '&:hover': {
            background: 'linear-gradient(135deg, #3D1654 0%, #9C1E7A 100%)',
          },
        },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: { textTransform: 'none', fontWeight: 600, minHeight: 48 },
      },
    },
    MuiCard: {
      styleOverrides: { root: { borderRadius: 16 } },
    },
    MuiChip: {
      styleOverrides: {
        colorPrimary: { background: UNIQUS.gradientSoft, color: '#fff' },
      },
    },
  },
});
