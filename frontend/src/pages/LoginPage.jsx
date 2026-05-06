import { useState } from 'react';
import {
  Box, Paper, Typography, TextField, Button, Alert, Stack, Tabs, Tab, Divider,
} from '@mui/material';
import { useAuth } from '../context/AuthContext.jsx';
import { UNIQUS } from '../theme.js';

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
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Login failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box component="form" onSubmit={submit}>
      {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}
      <Stack spacing={2}>
        <TextField
          label="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          fullWidth
          autoFocus
          autoComplete="username"
        />
        <TextField
          label="Password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          fullWidth
          autoComplete="current-password"
        />
        <Button type="submit" variant="contained" size="large" disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in'}
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
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Registration failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box component="form" onSubmit={submit}>
      {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}
      <Stack spacing={2}>
        <TextField
          label="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          fullWidth
          autoFocus
          autoComplete="username"
          helperText="3+ chars; letters, digits, . _ - allowed"
        />
        <TextField
          label="Display name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          fullWidth
          autoComplete="name"
          helperText="Shown in the sidebar (e.g. 'Toshit Tejasvat')"
        />
        <TextField
          label="Password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          fullWidth
          autoComplete="new-password"
          helperText="At least 6 characters"
        />
        <TextField
          label="Confirm password"
          type="password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          fullWidth
          autoComplete="new-password"
        />
        <Button type="submit" variant="contained" size="large" disabled={busy}>
          {busy ? 'Creating account…' : 'Create account'}
        </Button>
        <Typography variant="caption" color="text.secondary" align="center">
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
        alignItems: 'center',
        justifyContent: 'center',
        background: UNIQUS.gradient,
        p: 2,
      }}
    >
      <Paper
        elevation={0}
        sx={{
          p: 5,
          width: 460,
          borderRadius: 4,
          boxShadow: '0 24px 60px rgba(0,0,0,0.25)',
        }}
      >
        <Stack alignItems="center" spacing={2} mb={3}>
          <Box
            sx={{
              background: UNIQUS.gradient,
              borderRadius: 0,
              px: 4,
              py: 2.5,
              width: '100%',
              textAlign: 'center',
            }}
          >
            <Box
              component="img"
              src="/assets/uniqus_logo.png"
              alt="Uniqus"
              sx={{
                height: 48,
                width: 'auto',
                filter: 'brightness(0) invert(1)',
              }}
            />
          </Box>
          <Typography variant="h5" sx={{ mt: 1 }}>Master Data Profiler</Typography>
          <Typography variant="body2" color="text.secondary" align="center">
            {tab === 0
              ? 'Sign in to access your data quality workspace'
              : 'Create an account to get started'}
          </Typography>
        </Stack>

        <Tabs
          value={tab}
          onChange={(_, v) => setTab(v)}
          variant="fullWidth"
          sx={{ mb: 2.5, borderBottom: 1, borderColor: 'divider' }}
        >
          <Tab label="Sign in" />
          <Tab label="Sign up" />
        </Tabs>

        {tab === 0 ? <SignInForm /> : <SignUpForm onDone={() => setTab(0)} />}
      </Paper>
    </Box>
  );
}
