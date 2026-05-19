import { useEffect, useState, useMemo } from 'react';
import {
  Box, Stack, Typography, Button, Chip, Alert, LinearProgress, IconButton,
  TextField, Grid, Tooltip, Divider, Checkbox, InputAdornment,
} from '@mui/material';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import LinkOutlinedIcon from '@mui/icons-material/LinkOutlined';
import LinkOffOutlinedIcon from '@mui/icons-material/LinkOffOutlined';
import VisibilityOutlinedIcon from '@mui/icons-material/VisibilityOutlined';
import VisibilityOffOutlinedIcon from '@mui/icons-material/VisibilityOffOutlined';
import CloudSyncOutlinedIcon from '@mui/icons-material/CloudSyncOutlined';
import SearchOutlinedIcon from '@mui/icons-material/SearchOutlined';
import StorageOutlinedIcon from '@mui/icons-material/StorageOutlined';
import api from '../../api.js';
import ContentCard from '../../components/ContentCard.jsx';
import { useProject } from '../../context/ProjectContext.jsx';
import { useDataset } from '../../context/DatasetContext.jsx';

const FIELD_SX = { '& .MuiInputBase-input': { fontFamily: 'ui-monospace, Menlo, monospace', fontSize: 13 } };

function SecretField({ label, value, onChange }) {
  const [show, setShow] = useState(false);
  return (
    <TextField
      fullWidth size="small" label={label} value={value}
      onChange={(e) => onChange(e.target.value)}
      type={show ? 'text' : 'password'} autoComplete="off"
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

  // Credential form fields
  const [accountId, setAccountId] = useState('');
  const [consumerKey, setConsumerKey] = useState('');
  const [consumerSecret, setConsumerSecret] = useState('');
  const [tokenId, setTokenId] = useState('');
  const [tokenSecret, setTokenSecret] = useState('');

  // Dynamic table discovery
  const [availableTables, setAvailableTables] = useState(null); // null = not yet fetched
  const [tableSearch, setTableSearch] = useState('');
  const [selectedTables, setSelectedTables] = useState([]); // ordered: first = primary

  // UI state
  const [busy, setBusy] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [loadResult, setLoadResult] = useState(null);
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

  useEffect(() => {
    if (!isNetSuiteProject) return;
    loadStatus();
    setTestResult(null);
    setLoadResult(null);
    setError('');
    setAvailableTables(null);
    setSelectedTables([]);
    setTableSearch('');
  }, [isNetSuiteProject, active?.id]);

  // ── Credential form helpers ────────────────────────────────────────────

  const credentialsBody = () => ({
    account_id: accountId.trim(),
    consumer_key: consumerKey.trim(),
    consumer_secret: consumerSecret.trim(),
    token_id: tokenId.trim(),
    token_secret: tokenSecret.trim(),
  });

  const canSubmit = () => Object.values(credentialsBody()).every((v) => v.length > 0);

  const testConnection = async () => {
    if (!canSubmit()) return;
    setBusy(true); setError(''); setTestResult(null);
    try {
      const { data } = await api.post('/netsuite/test-connection', credentialsBody());
      setTestResult(data?.ok
        ? { ok: true, message: `Connected to ${data.account_label}. NetSuite returned ${data.rows_returned ?? 1} heartbeat row.` }
        : { ok: false, message: data?.error || 'Connection failed' });
    } catch (e) {
      setTestResult({ ok: false, message: e?.response?.data?.detail || 'Connection test failed' });
    } finally {
      setBusy(false);
    }
  };

  const saveConnection = async () => {
    if (!canSubmit()) return;
    setBusy(true); setError('');
    try {
      await api.post('/netsuite/credentials', credentialsBody());
      setConsumerKey(''); setConsumerSecret(''); setTokenId(''); setTokenSecret('');
      await loadStatus();
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not save credentials');
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!window.confirm('Remove the saved NetSuite credentials for this project?')) return;
    setBusy(true); setError(''); setLoadResult(null); setAvailableTables(null); setSelectedTables([]);
    try {
      await api.delete('/netsuite/credentials');
      await loadStatus();
    } catch (e) {
      setError(e?.response?.data?.detail || 'Disconnect failed');
    } finally {
      setBusy(false);
    }
  };

  // ── Dynamic table discovery ────────────────────────────────────────────

  const discoverTables = async () => {
    setBusy(true); setError(''); setAvailableTables(null); setSelectedTables([]);
    try {
      const { data } = await api.get('/netsuite/available-tables?probe=true');
      setAvailableTables(data?.tables || []);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not discover tables — check token permissions.');
    } finally {
      setBusy(false);
    }
  };

  const toggleTable = (tableName) => {
    setSelectedTables((prev) =>
      prev.includes(tableName) ? prev.filter((t) => t !== tableName) : [...prev, tableName]
    );
  };

  const filteredTables = useMemo(() => {
    if (!availableTables) return [];
    const q = tableSearch.toLowerCase();
    return q ? availableTables.filter((t) => t.toLowerCase().includes(q)) : availableTables;
  }, [availableTables, tableSearch]);

  const loadTables = async () => {
    if (selectedTables.length === 0) return;
    setBusy(true); setError(''); setLoadResult(null);
    try {
      const { data } = await api.post('/netsuite/load-tables', {
        tables: selectedTables,
        row_limit: 1000,
      });
      const loaded = (data?.loaded || []).length;
      const skipped = (data?.skipped || []).length;
      let message = `Loaded ${data?.primary_rows?.toLocaleString()} rows × ${data?.primary_columns} critical data elements from ${selectedTables[0]}`;
      if (loaded > 1) message += ` + ${loaded - 1} supplementary table${loaded - 1 === 1 ? '' : 's'}`;
      message += '.';
      if (skipped > 0) {
        const names = (data.skipped || []).map((s) => s.table).join(', ');
        message += ` Skipped (no permission): ${names}.`;
      }
      setLoadResult({ ok: true, message });
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
      {/* Header */}
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.5 }}>
        <CloudSyncOutlinedIcon sx={{ color: '#6A28A8' }} />
        <Typography sx={{ fontFamily: "'Montserrat', sans-serif", fontSize: 17, fontWeight: 700, color: '#1A1A1A' }}>
          NetSuite connection
        </Typography>
        {status.saved && (
          <Chip size="small" label="Connected"
            sx={{ height: 20, fontSize: '0.7rem', bgcolor: '#E6F4EC', color: '#2F8F57', fontWeight: 700 }} />
        )}
      </Stack>
      <Typography sx={{ fontSize: 12.5, color: '#555555', mb: 2 }}>
        Token-Based Authentication (TBA). Credentials are only sent to NetSuite over HTTPS — never logged or persisted in plaintext.
      </Typography>

      {busy && <LinearProgress sx={{ mb: 1.5 }} />}
      {error && <Alert severity="error" sx={{ mb: 1.5 }}>{error}</Alert>}

      {/* ── Credential entry form (when not yet connected) ── */}
      {!status.saved && (
        <Box>
          <Grid container spacing={1.5}>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth size="small" label="Account ID"
                placeholder="e.g. XXXXXXXX (or XXXXXXXX_SB1 for sandbox)"
                value={accountId} onChange={(e) => setAccountId(e.target.value)}
                autoComplete="off" inputProps={{ autoComplete: 'off' }}
                sx={FIELD_SX} helperText="Setup → Company → Company Information." />
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

          <Stack direction="row" spacing={1.5} sx={{ mt: 2 }}>
            <Button variant="outlined" startIcon={<LinkOutlinedIcon />}
              disabled={busy || !canSubmit()} onClick={testConnection}>
              Test connection
            </Button>
            <Button variant="contained" disabled={busy || !canSubmit()} onClick={saveConnection}>
              Save &amp; connect
            </Button>
          </Stack>
        </Box>
      )}

      {/* ── Connected state ── */}
      {status.saved && (
        <Box>
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }}>
            <Stack direction="row" spacing={1.5} alignItems="center">
              <CheckCircleOutlineIcon sx={{ color: '#2F8F57' }} />
              <Box>
                <Typography sx={{ fontSize: 13.5, fontWeight: 700, color: '#1A1A1A' }}>
                  Account {status.account_label || status.account_label_masked}
                </Typography>
                <Typography sx={{ fontSize: 11.5, color: '#8A8A8A' }}>
                  {status.via_env
                    ? 'Connected via system configuration — no setup required.'
                    : 'Credentials saved for this project.'}
                </Typography>
              </Box>
            </Stack>
            {!status.via_env && (
              <Tooltip title="Remove saved credentials from this project">
                <span>
                  <Button variant="text" size="small" startIcon={<LinkOffOutlinedIcon />}
                    onClick={disconnect} disabled={busy} sx={{ color: '#8A4848' }}>
                    Disconnect
                  </Button>
                </span>
              </Tooltip>
            )}
          </Stack>

          <Divider sx={{ my: 1.5 }} />

          {/* Discover tables */}
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
            <Box>
              <Typography sx={{ fontFamily: "'Montserrat', sans-serif", fontSize: 14, fontWeight: 700, color: '#1A1A1A' }}>
                Select tables to load
              </Typography>
              <Typography sx={{ fontSize: 12.5, color: '#555555' }}>
                Discover which tables your token can access, then pick the ones you want.
                The first selected table becomes the working dataset.
              </Typography>
            </Box>
            <Button
              variant="outlined"
              size="small"
              startIcon={<StorageOutlinedIcon />}
              disabled={busy}
              onClick={discoverTables}
              sx={{ whiteSpace: 'nowrap', ml: 2 }}
            >
              {availableTables === null ? 'Discover tables' : 'Refresh'}
            </Button>
          </Stack>

          {/* Table list */}
          {availableTables !== null && (
            <Box sx={{ mt: 1.5 }}>
              {availableTables.length === 0 ? (
                <Alert severity="warning">No tables found — the token may not have SuiteQL read access.</Alert>
              ) : (
                <>
                  <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
                    <TextField
                      size="small"
                      placeholder={`Search ${availableTables.length} tables…`}
                      value={tableSearch}
                      onChange={(e) => setTableSearch(e.target.value)}
                      sx={{ flex: 1 }}
                      InputProps={{
                        startAdornment: (
                          <InputAdornment position="start">
                            <SearchOutlinedIcon fontSize="small" sx={{ color: '#AAAAAA' }} />
                          </InputAdornment>
                        ),
                      }}
                    />
                    <Typography sx={{ fontSize: 12, color: '#8A8A8A', whiteSpace: 'nowrap' }}>
                      {selectedTables.length} selected
                    </Typography>
                    {selectedTables.length > 0 && (
                      <Button size="small" onClick={() => setSelectedTables([])}>Clear</Button>
                    )}
                  </Stack>

                  <Box
                    sx={{
                      maxHeight: 260,
                      overflowY: 'auto',
                      border: '1px solid #E7E6E6',
                      borderRadius: 1,
                      bgcolor: '#FAFAFA',
                    }}
                  >
                    {filteredTables.map((tableName) => {
                      const isChecked = selectedTables.includes(tableName);
                      const isPrimary = selectedTables[0] === tableName;
                      return (
                        <Stack
                          key={tableName}
                          direction="row"
                          alignItems="center"
                          spacing={1}
                          onClick={() => toggleTable(tableName)}
                          sx={{
                            px: 1.5,
                            py: 0.75,
                            cursor: 'pointer',
                            bgcolor: isChecked ? '#F4EEF9' : 'transparent',
                            borderBottom: '1px solid #F0EFEF',
                            '&:last-child': { borderBottom: 'none' },
                            '&:hover': { bgcolor: isChecked ? '#EDE5F7' : '#F5F5F5' },
                          }}
                        >
                          <Checkbox
                            size="small"
                            checked={isChecked}
                            onChange={() => toggleTable(tableName)}
                            onClick={(e) => e.stopPropagation()}
                            sx={{ p: 0, color: '#6A28A8', '&.Mui-checked': { color: '#6A28A8' } }}
                          />
                          <Typography
                            sx={{ fontFamily: 'ui-monospace, Menlo, monospace', fontSize: 13, flex: 1, color: '#1A1A1A' }}
                          >
                            {tableName}
                          </Typography>
                          {isPrimary && (
                            <Chip size="small" label="primary"
                              sx={{ height: 18, fontSize: '0.65rem', bgcolor: '#EDE5F7', color: '#6A28A8', fontWeight: 700 }} />
                          )}
                        </Stack>
                      );
                    })}
                    {filteredTables.length === 0 && (
                      <Typography sx={{ p: 2, fontSize: 13, color: '#8A8A8A', textAlign: 'center' }}>
                        No tables match "{tableSearch}"
                      </Typography>
                    )}
                  </Box>
                </>
              )}
            </Box>
          )}

          {loadResult && (
            <Alert severity={loadResult.ok ? 'success' : 'error'} sx={{ mt: 1.5 }}>
              {loadResult.message}
            </Alert>
          )}

          {availableTables !== null && selectedTables.length > 0 && (
            <Button
              variant="contained"
              disabled={busy}
              onClick={loadTables}
              sx={{ mt: 1.5, fontWeight: 700 }}
            >
              {busy
                ? 'Loading from NetSuite…'
                : `Load ${selectedTables.length} table${selectedTables.length === 1 ? '' : 's'}`}
            </Button>
          )}
        </Box>
      )}
    </ContentCard>
  );
}
