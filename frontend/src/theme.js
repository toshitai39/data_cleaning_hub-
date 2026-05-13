import { createTheme } from '@mui/material/styles';

// Uniqus brand palette — deep purple + magenta gradient on a calm,
// neutral content area. Sidebar uses its own dark token set in index.css.
export const UNIQUS = {
  purple:        '#492079',
  purpleDeep:    '#2A124A',
  magenta:       '#B31E7C',
  accent:        '#6A28A8',
  accentBg:      '#F4ECF9',
  gradient:      'linear-gradient(135deg, #492079 0%, #B31E7C 100%)',
  gradientSoft:  'linear-gradient(135deg, rgba(73,32,121,0.12) 0%, rgba(179,30,124,0.12) 100%)',
  border:        '#E7E6E6',
  border2:       '#DDD6E5',
  bg:            '#FFFFFF',
  bg2:           '#F7F5FA',
  bg3:           '#F1ECF6',
  fg:            '#1A1A1A',
  fg2:           '#555555',
  fg3:           '#8A8A8A',
};

const FONT_DISPLAY = "'Montserrat', system-ui, -apple-system, BlinkMacSystemFont, sans-serif";
const FONT_BODY = "'Open Sans', system-ui, -apple-system, BlinkMacSystemFont, sans-serif";

export const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: UNIQUS.accent, light: UNIQUS.magenta, dark: UNIQUS.purpleDeep, contrastText: '#fff' },
    secondary: { main: UNIQUS.magenta, contrastText: '#fff' },
    success: { main: '#2F8F57' },
    warning: { main: '#C88A1A' },
    error: { main: '#D14343' },
    info: { main: '#2A6FDB' },
    background: { default: UNIQUS.bg2, paper: UNIQUS.bg },
    text: { primary: UNIQUS.fg, secondary: UNIQUS.fg2, disabled: UNIQUS.fg3 },
    divider: UNIQUS.border,
  },
  shape: { borderRadius: 10 },
  typography: {
    fontFamily: FONT_BODY,
    h1: { fontFamily: FONT_DISPLAY, fontWeight: 800, letterSpacing: '-0.02em' },
    h2: { fontFamily: FONT_DISPLAY, fontWeight: 800, letterSpacing: '-0.02em' },
    h3: { fontFamily: FONT_DISPLAY, fontWeight: 700, letterSpacing: '-0.02em' },
    h4: { fontFamily: FONT_DISPLAY, fontWeight: 700, letterSpacing: '-0.01em' },
    h5: { fontFamily: FONT_DISPLAY, fontWeight: 700, letterSpacing: '-0.01em' },
    h6: { fontFamily: FONT_DISPLAY, fontWeight: 700 },
    subtitle1: { fontWeight: 600 },
    subtitle2: { fontWeight: 600 },
    button: { textTransform: 'none', fontWeight: 600, letterSpacing: 0 },
    overline: { fontFamily: FONT_DISPLAY, fontWeight: 700, letterSpacing: '0.12em' },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: { backgroundColor: UNIQUS.bg2 },
      },
    },
    MuiPaper: {
      defaultProps: { elevation: 0 },
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          border: `1px solid ${UNIQUS.border}`,
          boxShadow: '0 1px 2px rgba(73,32,121,0.04)',
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: { borderRadius: 8, paddingLeft: 16, paddingRight: 16 },
        containedPrimary: {
          background: UNIQUS.gradient,
          boxShadow: '0 2px 8px rgba(73,32,121,0.20)',
          '&:hover': {
            background: 'linear-gradient(135deg, #2A124A 0%, #492079 50%, #B31E7C 100%)',
            boxShadow: '0 4px 14px rgba(73,32,121,0.30)',
          },
          // Default MUI disabled state on the purple gradient renders as
          // unreadable dark-grey-on-dark. Force a neutral light-grey treatment
          // so every disabled primary button across the app stays legible.
          '&.Mui-disabled': {
            background: '#E7E6E6',
            color: '#8A8A8A',
            boxShadow: 'none',
          },
        },
        outlined: { borderColor: UNIQUS.border },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: { textTransform: 'none', fontWeight: 600, minHeight: 44, fontFamily: FONT_BODY },
      },
    },
    MuiCard: {
      defaultProps: { elevation: 0 },
      styleOverrides: { root: { borderRadius: 12, border: `1px solid ${UNIQUS.border}` } },
    },
    MuiChip: {
      styleOverrides: {
        root: { fontWeight: 600, borderRadius: 8 },
        colorPrimary: { background: UNIQUS.accentBg, color: UNIQUS.accent },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        head: {
          fontWeight: 700,
          fontSize: '0.72rem',
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          color: UNIQUS.fg3,
          backgroundColor: '#FBFAFC',
        },
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: { borderRadius: 10, border: '1px solid', borderColor: 'transparent' },
        standardInfo: { backgroundColor: '#E6F0FC', color: '#1E3A8A', borderColor: '#BFDBFE' },
        standardSuccess: { backgroundColor: '#E8F4ED', color: '#14532D', borderColor: '#BBF7D0' },
        standardWarning: { backgroundColor: '#FCF3E2', color: '#7A4F09', borderColor: '#FDE68A' },
        standardError: { backgroundColor: '#FBEAEA', color: '#7F1D1D', borderColor: '#FCA5A5' },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          '& fieldset': { borderColor: UNIQUS.border },
          '&:hover fieldset': { borderColor: UNIQUS.border2 },
        },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          backgroundColor: UNIQUS.purpleDeep,
          fontSize: '0.75rem',
        },
        arrow: { color: UNIQUS.purpleDeep },
      },
    },
  },
});
