import { useState } from 'react';
import {
  Box, Typography, TextField, Button, Alert, Stack, Tabs, Tab,
} from '@mui/material';
import { useAuth } from '../context/AuthContext.jsx';

function SignInForm() {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setErr('');
    setBusy(true);
    try {
      await login(username, password);
    } catch (e2) {
      setErr(e2?.response?.data?.detail || 'Login failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box component="form" onSubmit={submit}>
      {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}
      <Stack spacing={2.5}>
        <Box>
          <Typography
            sx={{
              fontFamily: "'Open Sans', sans-serif",
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: '0.12em',
              color: '#8A8A8A',
              textTransform: 'uppercase',
              mb: 0.75,
            }}
          >
            Username
          </Typography>
          <TextField
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            fullWidth
            autoFocus
            autoComplete="username"
            placeholder="you@company.com"
            size="medium"
          />
        </Box>
        <Box>
          <Typography
            sx={{
              fontFamily: "'Open Sans', sans-serif",
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: '0.12em',
              color: '#8A8A8A',
              textTransform: 'uppercase',
              mb: 0.75,
            }}
          >
            Password
          </Typography>
          <TextField
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            fullWidth
            autoComplete="current-password"
            placeholder="••••••••"
            size="medium"
          />
        </Box>
        <Button
          type="submit"
          variant="contained"
          size="large"
          disabled={busy}
          sx={{ mt: 1, py: 1.5, fontSize: 15, fontWeight: 700 }}
        >
          {busy ? 'Signing in…' : 'Continue'}
        </Button>
      </Stack>
    </Box>
  );
}

function SignUpForm({ onDone }) {
  const { register } = useAuth();
  const [username, setUsername] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  const validate = () => {
    if (username.trim().length < 3) return 'Username must be at least 3 characters';
    if (!/^[A-Za-z0-9._-]+$/.test(username.trim())) {
      return 'Username may only contain letters, digits, dot, underscore, hyphen';
    }
    if (!name.trim()) return 'Display name is required';
    if (password.length < 6) return 'Password must be at least 6 characters';
    if (password !== confirm) return 'Passwords do not match';
    return null;
  };

  const submit = async (e) => {
    e.preventDefault();
    setErr('');
    const v = validate();
    if (v) { setErr(v); return; }
    setBusy(true);
    try {
      await register(username.trim(), password, name.trim());
      onDone?.();
    } catch (e2) {
      setErr(e2?.response?.data?.detail || 'Registration failed');
    } finally {
      setBusy(false);
    }
  };

  const LabelEyebrow = ({ children }) => (
    <Typography
      sx={{
        fontFamily: "'Open Sans', sans-serif",
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: '0.12em',
        color: '#8A8A8A',
        textTransform: 'uppercase',
        mb: 0.75,
      }}
    >
      {children}
    </Typography>
  );

  return (
    <Box component="form" onSubmit={submit}>
      {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}
      <Stack spacing={2}>
        <Box>
          <LabelEyebrow>Username</LabelEyebrow>
          <TextField
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            fullWidth
            autoFocus
            autoComplete="username"
            placeholder="jdoe"
            helperText="3+ chars; letters, digits, . _ - allowed"
          />
        </Box>
        <Box>
          <LabelEyebrow>Display name</LabelEyebrow>
          <TextField
            value={name}
            onChange={(e) => setName(e.target.value)}
            fullWidth
            autoComplete="name"
            placeholder="Jane Doe"
            helperText="Shown in the sidebar"
          />
        </Box>
        <Box>
          <LabelEyebrow>Password</LabelEyebrow>
          <TextField
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            fullWidth
            autoComplete="new-password"
            placeholder="••••••••"
            helperText="At least 6 characters"
          />
        </Box>
        <Box>
          <LabelEyebrow>Confirm password</LabelEyebrow>
          <TextField
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            fullWidth
            autoComplete="new-password"
            placeholder="••••••••"
          />
        </Box>
        <Button
          type="submit"
          variant="contained"
          size="large"
          disabled={busy}
          sx={{ mt: 1, py: 1.5, fontSize: 15, fontWeight: 700 }}
        >
          {busy ? 'Creating account…' : 'Create account'}
        </Button>
        <Typography sx={{ fontSize: 12, color: '#8A8A8A', textAlign: 'center' }}>
          You will be signed in automatically after sign-up.
        </Typography>
      </Stack>
    </Box>
  );
}

export default function LoginPage() {
  const [tab, setTab] = useState(0);

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: { xs: 'column', md: 'row' },
        bgcolor: '#FFFFFF',
      }}
    >
      {/* ─── LEFT: dark hero ─────────────────────────────────────── */}
      <Box
        sx={{
          flex: { xs: 'none', md: 1 },
          minHeight: { xs: 280, md: 'auto' },
          background: 'linear-gradient(160deg, #1B0E3D 0%, #2A124A 40%, #492079 100%)',
          color: '#FFFFFF',
          position: 'relative',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          px: { xs: 4, md: 8 },
          py: { xs: 4, md: 6 },
          overflow: 'hidden',
        }}
      >
        {/* soft radial highlight */}
        <Box
          sx={{
            position: 'absolute',
            top: '20%',
            right: '-15%',
            width: 480,
            height: 480,
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(179,30,124,0.35) 0%, rgba(179,30,124,0) 70%)',
            pointerEvents: 'none',
          }}
        />

        <Box sx={{ position: 'relative' }}>
          <Box
            component="img"
            src="/assets/uniqus_logo.png"
            alt="Uniqus"
            sx={{
              height: 40,
              width: 'auto',
              filter: 'brightness(0) invert(1)',
              display: 'block',
            }}
          />
        </Box>

        <Box sx={{ position: 'relative', maxWidth: 520 }}>
          <Typography
            sx={{
              fontFamily: "'Montserrat', sans-serif",
              fontSize: 12,
              fontWeight: 700,
              letterSpacing: '0.2em',
              color: 'rgba(255,255,255,0.7)',
              textTransform: 'uppercase',
              mb: 2,
            }}
          >
            Welcome
          </Typography>
          <Typography
            sx={{
              fontFamily: "'Montserrat', sans-serif",
              fontSize: { xs: 36, md: 56 },
              fontWeight: 800,
              lineHeight: 1.05,
              letterSpacing: '-0.02em',
              color: '#FFFFFF',
              mb: 2.5,
            }}
          >
            Master Data{' '}
            <Box component="span" sx={{ fontStyle: 'italic', fontWeight: 700 }}>
              Profiler
            </Box>
          </Typography>
          <Typography
            sx={{
              fontFamily: "'Open Sans', sans-serif",
              fontSize: 16,
              lineHeight: 1.6,
              color: 'rgba(255,255,255,0.78)',
              maxWidth: 440,
            }}
          >
            AI-driven data quality for enterprise teams. Profile, validate and
            cleanse master data — sign in with your work account.
          </Typography>
        </Box>

        <Box
          sx={{
            position: 'relative',
            display: 'flex',
            gap: 2,
            alignItems: 'center',
            fontSize: 12,
            color: 'rgba(255,255,255,0.55)',
          }}
        >
          <Typography sx={{ fontSize: 12, letterSpacing: '0.04em' }}>
            Secure sign-in
          </Typography>
          <Box sx={{ width: 3, height: 3, borderRadius: '50%', bgcolor: 'rgba(255,255,255,0.4)' }} />
          <Typography sx={{ fontSize: 12, letterSpacing: '0.04em' }}>
            SSO-ready
          </Typography>
          <Box sx={{ width: 3, height: 3, borderRadius: '50%', bgcolor: 'rgba(255,255,255,0.4)' }} />
          <Typography sx={{ fontSize: 12, letterSpacing: '0.04em' }}>
            Enterprise-ready
          </Typography>
        </Box>
      </Box>

      {/* ─── RIGHT: form column ──────────────────────────────────── */}
      <Box
        sx={{
          flex: { xs: 'none', md: 1 },
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          bgcolor: '#FFFFFF',
          px: { xs: 3, sm: 6, md: 10 },
          py: { xs: 5, md: 6 },
          position: 'relative',
        }}
      >
        <Box sx={{ maxWidth: 440, width: '100%', mx: 'auto', flex: { xs: 'none', md: 1 }, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
          <Typography
            sx={{
              fontFamily: "'Montserrat', sans-serif",
              fontSize: { xs: 28, md: 36 },
              fontWeight: 800,
              letterSpacing: '-0.02em',
              color: '#1A1A1A',
              mb: 1,
            }}
          >
            {tab === 0 ? 'Sign in' : 'Create account'}
          </Typography>
          <Typography
            sx={{
              fontSize: 15,
              color: '#555555',
              mb: 3.5,
            }}
          >
            {tab === 0
              ? 'Use your work credentials to access your workspace.'
              : 'Start with a new account in under a minute.'}
          </Typography>

          <Tabs
            value={tab}
            onChange={(_, v) => setTab(v)}
            sx={{
              mb: 3,
              borderBottom: '1px solid #E7E6E6',
              minHeight: 40,
              '& .MuiTab-root': {
                minHeight: 40,
                fontWeight: 600,
                fontSize: 14,
                textTransform: 'none',
                px: 0,
                mr: 4,
              },
            }}
            TabIndicatorProps={{ sx: { height: 2.5, borderRadius: 2, bgcolor: '#6A28A8' } }}
          >
            <Tab label="Sign in" />
            <Tab label="Sign up" />
          </Tabs>

          {tab === 0 ? <SignInForm /> : <SignUpForm onDone={() => setTab(0)} />}
        </Box>

        <Box
          sx={{
            mt: { xs: 4, md: 0 },
            position: { md: 'absolute' },
            bottom: { md: 32 },
            right: { md: 40 },
            textAlign: { xs: 'center', md: 'right' },
          }}
        >
          <Typography sx={{ fontSize: 11, color: '#8A8A8A', letterSpacing: '0.02em' }}>
            © Uniqus Consultech · Master Data Profiler
          </Typography>
        </Box>
      </Box>
    </Box>
  );
}
