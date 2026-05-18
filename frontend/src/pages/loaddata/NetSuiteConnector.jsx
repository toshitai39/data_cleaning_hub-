import { useEffect, useState } from 'react';
import {
  Box, Stack, Typography, Button, Chip, Alert, LinearProgress, IconButton,
  TextField, Grid, Tooltip, Divider,
} from '@mui/material';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import LinkOutlinedIcon from '@mui/icons-material/LinkOutlined';
import LinkOffOutlinedIcon from '@mui/icons-material/LinkOffOutlined';
import VisibilityOutlinedIcon from '@mui/icons-material/VisibilityOutlined';
import VisibilityOffOutlinedIcon from '@mui/icons-material/VisibilityOffOutlined';
import CloudSyncOutlinedIcon from '@mui/icons-material/CloudSyncOutlined';
import api from '../../api.js';
import ContentCard from '../../components/ContentCard.jsx';
import { useProject } from '../../context/ProjectContext.jsx';
import { useDataset } from '../../context/DatasetContext.jsx';

const FIELD_SX = { '& .MuiInputBase-input': { fontFamily: 'ui-monospace, Menlo, monospace', fontSize: 13 } };

function SecretField({ label, value, onChange, autoComplete }) {
  // Tokens are long opaque blobs — peek toggle lets the steward verify
  // a paste before submitting without re-revealing on every keystroke.
  const [show, setShow] = useState(false);
  return (
    <TextField
      fullWidth
      size="small"
      label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      type={show ? 'text' : 'password'}
      autoComplete={autoComplete || 'off'}
      sx={FIELD_SX}
      InputProps={{
        endAdornment: (
          <IconButton size="small" onClick={() => setShow((s) => !s)} tabIndex={-1}>
            {show ? <VisibilityOffOutlinedIcon fontSize="small" /> : <VisibilityOutlinedIcon fontSize="small" />}
          </IconButton>
        ),
      }}
    />
  );
}

export default function NetSuiteConnector({ onLoaded }) {
  const { active, refresh: refreshProjects } = useProject();
  const { refresh: refreshDataset } = useDataset();

  const [status, setStatus] = useState({ saved: false });
  const [statusLoaded, setStatusLoaded] = useState(false);
  const [streams, setStreams] = useState([]);   // catalog of all NetSuite streams
  const [stream, setStream] = useState(null);   // the one matching the active project

  // Credential form
  const [accountId, setAccountId] = useState('');
  const [consumerKey, setConsumerKey] = useState('');
  const [consumerSecret, setConsumerSecret] = useState('');
  const [tokenId, setTokenId] = useState('');
  const [tokenSecret, setTokenSecret] = useState('');

  // UI state
  const [busy, setBusy] = useState(false);
  const [testResult, setTestResult] = useState(null);     // {ok, message}
  const [savedResult, setSavedResult] = useState(null);   // {ok, message}
  const [loadResult, setLoadResult] = useState(null);     // {ok, message}
  const [error, setError] = useState('');

  const isNetSuiteProject = active?.system?.id === 'netsuite';

  const loadStatus = async () => {
    try {
      const { data } = await api.get('/netsuite/credentials/status');
      setStatus(data || { saved: false });
    } catch (_) {
      setStatus({ saved: false });
    } finally {
      setStatusLoaded(true);
    }
  };

  const loadStreams = async () => {
    try {
      const { data } = await api.get('/netsuite/streams');
      setStreams(data?.streams || []);
    } catch (_) {
      setStreams([]);
    }
  };

  useEffect(() => {
    if (!isNetSuiteProject) return;
    loadStatus();
    loadStreams();
    // Reset transient banners when the active project changes.
    setTestResult(null);
    setSavedResult(null);
    setLoadResult(null);
    setError('');
  }, [isNetSuiteProject, active?.id]);

  useEffect(() => {
    if (!active?.stream?.id) { setStream(null); return; }
    setStream(streams.find((s) => s.id === active.stream.id) || null);
  }, [streams, active?.stream?.id]);

  const credentialsBody = () => ({
    account_id: accountId.trim(),
    consumer_key: consumerKey.trim(),
    consumer_secret: consumerSecret.trim(),
    token_id: tokenId.trim(),
    token_secret: tokenSecret.trim(),
  });

  const canSubmit = () => {
    const b = credentialsBody();
    return Object.values(b).every((v) => v.length > 0);
  };

  const testConnection = async () => {
    if (!canSubmit()) return;
    setBusy(true); setError(''); setTestResult(null);
    try {
      const { data } = await api.post('/netsuite/test-connection', credentialsBody());
      if (data?.ok) {
        setTestResult({
          ok: true,
          message: `Connected to ${data.account_label}. NetSuite returned ${data.rows_returned ?? 1} heartbeat row.`,
        });
      } else {
        setTestResult({ ok: false, message: data?.error || 'Connection failed' });
      }
    } catch (e) {
      setTestResult({
        ok: false,
        message: e?.response?.data?.detail || 'Connection test failed',
      });
    } finally {
      setBusy(false);
    }
  };

  const saveConnection = async () => {
    if (!canSubmit()) return;
    setBusy(true); setError(''); setSavedResult(null);
    try {
      const { data } = await api.post('/netsuite/credentials', credentialsBody());
      setSavedResult({ ok: true, message: `Saved encrypted credentials for ${data.account_label}.` });
      // Clear the form so the secrets aren't sitting in DOM state any longer
      // than necessary — the steward can re-enter them if they want to rotate.
      setConsumerKey(''); setConsumerSecret(''); setTokenId(''); setTokenSecret('');
      await loadStatus();
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not save credentials');
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!window.confirm('Remove the saved NetSuite credentials for this project? You will need to re-enter them next time.')) return;
    setBusy(true); setError(''); setSavedResult(null); setLoadResult(null);
    try {
      await api.delete('/netsuite/credentials');
      await loadStatus();
    } catch (e) {
      setError(e?.response?.data?.detail || 'Disconnect failed');
    } finally {
      setBusy(false);
    }
  };

  const loadStream = async (primaryOnly) => {
    if (!stream) return;
    setBusy(true); setError(''); setLoadResult(null);
    try {
      const body = { stream: stream.id, primary_only: !!primaryOnly, row_limit: 1000 };
      const { data } = await api.post('/netsuite/load-stream', body);
      const tablesLoaded = (data?.loaded || []).length;
      setLoadResult({
        ok: true,
        message: `Loaded ${data?.primary_rows?.toLocaleString()} rows × ${data?.primary_columns} columns from the primary table (${tablesLoaded} table${tablesLoaded === 1 ? '' : 's'} fetched).`,
      });
      await Promise.all([refreshProjects(), refreshDataset()]);
      onLoaded?.();
    } catch (e) {
      setError(e?.response?.data?.detail || 'Load from NetSuite failed');
    } finally {
      setBusy(false);
    }
  };

  if (!isNetSuiteProject) return null;
  if (!statusLoaded) return null;

  return (
    <ContentCard sx={{ mb: 2.5, p: 2.5 }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.5 }}>
        <CloudSyncOutlinedIcon sx={{ color: '#6A28A8' }} />
        <Typography
          sx={{
            fontFamily: "'Montserrat', sans-serif",
            fontSize: 17,
            fontWeight: 700,
            color: '#1A1A1A',
          }}
        >
          NetSuite connection
        </Typography>
        {status.saved && (
          <Chip
            size="small"
            label="Connected"
            sx={{ height: 20, fontSize: '0.7rem', bgcolor: '#E6F4EC', color: '#2F8F57', fontWeight: 700 }}
          />
        )}
      </Stack>
      <Typography sx={{ fontSize: 12.5, color: '#555555', mb: 2 }}>
        Token-Based Authentication (TBA). Credentials are encrypted at rest and only sent to NetSuite over HTTPS — never logged or persisted in plaintext.
      </Typography>

      {busy && <LinearProgress sx={{ mb: 1.5 }} />}
      {error && <Alert severity="error" sx={{ mb: 1.5 }}>{error}</Alert>}

      {!status.saved && (
        <Box>
          <Grid container spacing={1.5}>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                size="small"
                label="Account ID"
                placeholder="e.g. XX1234567 (or XX1234567_SB1 for sandbox)"
                value={accountId}
                onChange={(e) => setAccountId(e.target.value)}
                sx={FIELD_SX}
                helperText="From Setup → Company → Company Information."
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <SecretField label="Consumer Key" value={consumerKey} onChange={setConsumerKey} />
            </Grid>
            <Grid item xs={12} sm={6}>
              <SecretField label="Consumer Secret" value={consumerSecret} onChange={setConsumerSecret} />
            </Grid>
            <Grid item xs={12} sm={6}>
              <SecretField label="Token ID" value={tokenId} onChange={setTokenId} />
            </Grid>
            <Grid item xs={12} sm={6}>
              <SecretField label="Token Secret" value={tokenSecret} onChange={setTokenSecret} />
            </Grid>
          </Grid>

          {testResult && (
            <Alert severity={testResult.ok ? 'success' : 'error'} sx={{ mt: 1.5 }}>
              {testResult.message}
            </Alert>
          )}
          {savedResult && (
            <Alert severity="success" sx={{ mt: 1.5 }}>
              {savedResult.message}
            </Alert>
          )}

          <Stack direction="row" spacing={1.5} sx={{ mt: 2 }}>
            <Button
              variant="outlined"
              startIcon={<LinkOutlinedIcon />}
              disabled={busy || !canSubmit()}
              onClick={testConnection}
            >
              Test connection
            </Button>
            <Button
              variant="contained"
              disabled={busy || !canSubmit()}
              onClick={saveConnection}
            >
              Save &amp; connect
            </Button>
          </Stack>
        </Box>
      )}

      {status.saved && (
        <Box>
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }}>
            <Stack direction="row" spacing={1.5} alignItems="center">
              <CheckCircleOutlineIcon sx={{ color: '#2F8F57' }} />
              <Box>
                <Typography sx={{ fontSize: 13.5, fontWeight: 700, color: '#1A1A1A' }}>
                  Account {status.account_label_masked || status.account_label}
                </Typography>
                <Typography sx={{ fontSize: 11.5, color: '#8A8A8A' }}>
                  Credentials are encrypted on this project and ready to fetch.
                </Typography>
              </Box>
            </Stack>
            <Tooltip title="Remove saved NetSuite credentials from this project">
              <span>
                <Button
                  variant="text"
                  size="small"
                  startIcon={<LinkOffOutlinedIcon />}
                  onClick={disconnect}
                  disabled={busy}
                  sx={{ color: '#8A4848' }}
                >
                  Disconnect
                </Button>
              </span>
            </Tooltip>
          </Stack>

          <Divider sx={{ my: 1.5 }} />

          {!stream && (
            <Alert severity="warning">
              This project's stream ({active?.stream?.label}) doesn't have a NetSuite query template yet.
            </Alert>
          )}

          {stream && (
            <Box>
              <Typography
                sx={{
                  fontFamily: "'Montserrat', sans-serif",
                  fontSize: 14,
                  fontWeight: 700,
                  color: '#1A1A1A',
                  mb: 0.5,
                }}
              >
                Fetch {stream.label}
              </Typography>
              <Typography sx={{ fontSize: 12.5, color: '#555555', mb: 1.5 }}>
                Pulls every supported table for this stream via SuiteQL. The primary table is loaded as the working dataset; extension and lookup tables are stashed for multi-table joins.
              </Typography>

              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
                  gap: 1.25,
                  mb: 2,
                }}
              >
                {stream.tables.map((t) => (
                  <Box
                    key={t.id}
                    sx={{
                      border: '1px solid #E7E6E6',
                      borderRadius: 1,
                      bgcolor: '#FBFAFC',
                      px: 1.5,
                      py: 1.25,
                    }}
                  >
                    <Stack direction="row" spacing={0.75} alignItems="center" sx={{ mb: 0.5 }}>
                      <Typography
                        sx={{
                          fontFamily: 'ui-monospace, Menlo, monospace',
                          fontSize: 12,
                          fontWeight: 700,
                          color: '#6A28A8',
                        }}
                      >
                        {t.id}
                      </Typography>
                      <Chip
                        size="small"
                        label={t.role || 'primary'}
                        variant="outlined"
                        sx={{ height: 18, fontSize: '0.65rem' }}
                      />
                      {t.required && (
                        <Chip
                          size="small"
                          label="required"
                          sx={{ height: 18, fontSize: '0.65rem', bgcolor: '#FBEAEA', color: '#D14343' }}
                        />
                      )}
                      {!t.has_query && (
                        <Chip
                          size="small"
                          label="no template"
                          sx={{ height: 18, fontSize: '0.65rem', bgcolor: '#F1ECF6', color: '#8A8A8A' }}
                        />
                      )}
                    </Stack>
                    <Typography sx={{ fontSize: 12.5, fontWeight: 600, color: '#1A1A1A' }}>
                      {t.label}
                    </Typography>
                    {t.description && (
                      <Typography sx={{ fontSize: 11.5, color: '#8A8A8A', mt: 0.25 }}>
                        {t.description}
                      </Typography>
                    )}
                  </Box>
                ))}
              </Box>

              {loadResult && (
                <Alert severity={loadResult.ok ? 'success' : 'error'} sx={{ mb: 1.5 }}>
                  {loadResult.message}
                </Alert>
              )}

              <Stack direction="row" spacing={1.5}>
                <Button
                  variant="outlined"
                  disabled={busy}
                  onClick={() => loadStream(true)}
                >
                  Primary table only
                </Button>
                <Button
                  variant="contained"
                  disabled={busy}
                  onClick={() => loadStream(false)}
                  sx={{ fontWeight: 700 }}
                >
                  {busy ? 'Loading from NetSuite…' : `Load all ${stream.tables.length} table${stream.tables.length === 1 ? '' : 's'}`}
                </Button>
              </Stack>
            </Box>
          )}
        </Box>
      )}
    </ContentCard>
  );
}
