import { useEffect, useMemo, useState } from 'react';
import {
  Accordion, AccordionSummary, AccordionDetails, Box, Grid, TextField, MenuItem,
  Button, Stack, Alert, Checkbox, FormControlLabel, Typography, LinearProgress,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import api from '../../api.js';

export default function DbConnector({ onLoaded }) {
  const [engines, setEngines] = useState([]);
  const [engineLabel, setEngineLabel] = useState('');
  const [useRawUrl, setUseRawUrl] = useState(false);
  const [rawUrl, setRawUrl] = useState('');
  const [host, setHost] = useState('localhost');
  const [port, setPort] = useState(5432);
  const [database, setDatabase] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [dbPath, setDbPath] = useState('');
  const [bqProject, setBqProject] = useState('');
  const [sfAccount, setSfAccount] = useState('');
  const [sfDatabase, setSfDatabase] = useState('');
  const [sfUser, setSfUser] = useState('');
  const [sfPass, setSfPass] = useState('');
  const [tables, setTables] = useState([]);
  const [tablePick, setTablePick] = useState('');
  const [customQuery, setCustomQuery] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const [connectedUrl, setConnectedUrl] = useState('');

  useEffect(() => {
    api.get('/data/db/engines').then((r) => {
      setEngines(r.data);
      if (r.data.length > 0 && !engineLabel) setEngineLabel(r.data[0].label);
    }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const meta = useMemo(
    () => engines.find((e) => e.label === engineLabel),
    [engines, engineLabel],
  );

  useEffect(() => {
    if (meta?.default_port) setPort(meta.default_port);
  }, [meta]);

  const buildAndConnect = async () => {
    setBusy(true); setErr(''); setMsg(''); setTables([]); setConnectedUrl('');
    try {
      let url = rawUrl;
      if (!useRawUrl) {
        const params = { engine_label: engineLabel };
        if (meta?.is_file_based) {
          params.database = dbPath;
        } else if (meta?.is_cloud) {
          params.database = bqProject;
        } else if (meta?.is_snowflake) {
          params.host = sfAccount;
          params.database = sfDatabase;
          params.username = sfUser;
          params.password = sfPass;
        } else {
          params.host = host; params.port = port; params.database = database;
          params.username = username; params.password = password;
        }
        const built = await api.post('/data/db/build-url', params);
        url = built.data.url;
      }
      const conn = await api.post('/data/db/connect', { url });
      setTables(conn.data.tables);
      setConnectedUrl(url);
      setMsg(`Connected — ${conn.data.tables.length} tables found`);
      if (conn.data.tables.length > 0) setTablePick(conn.data.tables[0]);
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Connection failed');
    } finally { setBusy(false); }
  };

  const loadTable = async () => {
    if (!connectedUrl) return;
    setBusy(true); setErr(''); setMsg('');
    try {
      const { data } = await api.post('/data/db/load', {
        url: connectedUrl, table: tablePick, custom_query: customQuery,
      });
      setMsg(`Loaded ${data.rows.toLocaleString()} rows from database`);
      onLoaded?.();
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Load failed');
    } finally { setBusy(false); }
  };

  const renderEngineFields = () => {
    if (useRawUrl) {
      return (
        <TextField fullWidth size="small" label="SQLAlchemy URL" value={rawUrl}
          onChange={(e) => setRawUrl(e.target.value)}
          placeholder="postgresql+psycopg2://user:pass@host:5432/mydb" />
      );
    }
    if (meta?.is_file_based) {
      return (
        <TextField fullWidth size="small"
          label="Database file path (.db / .sqlite / .duckdb)"
          value={dbPath} onChange={(e) => setDbPath(e.target.value)} />
      );
    }
    if (meta?.is_cloud) {
      return (
        <TextField fullWidth size="small" label="GCP Project ID"
          value={bqProject} onChange={(e) => setBqProject(e.target.value)} />
      );
    }
    if (meta?.is_snowflake) {
      return (
        <Grid container spacing={1.5}>
          <Grid item xs={12} sm={6}>
            <TextField fullWidth size="small" label="Account (e.g. xy12345.us-east-1)"
              value={sfAccount} onChange={(e) => setSfAccount(e.target.value)} />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField fullWidth size="small" label="Username"
              value={sfUser} onChange={(e) => setSfUser(e.target.value)} />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField fullWidth size="small" label="Database"
              value={sfDatabase} onChange={(e) => setSfDatabase(e.target.value)} />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField fullWidth size="small" label="Password" type="password"
              value={sfPass} onChange={(e) => setSfPass(e.target.value)} />
          </Grid>
        </Grid>
      );
    }
    return (
      <Grid container spacing={1.5}>
        <Grid item xs={6} sm={4}>
          <TextField fullWidth size="small" label="Host" value={host}
            onChange={(e) => setHost(e.target.value)} />
        </Grid>
        <Grid item xs={6} sm={2}>
          <TextField fullWidth size="small" type="number" label="Port" value={port}
            onChange={(e) => setPort(parseInt(e.target.value || '0', 10))} />
        </Grid>
        <Grid item xs={12} sm={6}>
          <TextField fullWidth size="small" label="Database" value={database}
            onChange={(e) => setDatabase(e.target.value)} />
        </Grid>
        <Grid item xs={12} sm={6}>
          <TextField fullWidth size="small" label="Username" value={username}
            onChange={(e) => setUsername(e.target.value)} />
        </Grid>
        <Grid item xs={12} sm={6}>
          <TextField fullWidth size="small" label="Password" type="password" value={password}
            onChange={(e) => setPassword(e.target.value)} />
        </Grid>
      </Grid>
    );
  };

  return (
    <Accordion sx={{ mt: 2 }}>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Typography>Connect to Database</Typography>
      </AccordionSummary>
      <AccordionDetails>
        <Stack spacing={2}>
          <TextField select size="small" label="Database Engine"
            value={engineLabel} onChange={(e) => setEngineLabel(e.target.value)}
            sx={{ maxWidth: 320 }}>
            {engines.map((e) => (
              <MenuItem key={e.label} value={e.label}>{e.label}</MenuItem>
            ))}
          </TextField>

          {meta && (
            meta.driver_installed
              ? <Typography variant="caption" color="success.main">Driver: installed</Typography>
              : <Alert severity="warning">Driver not installed. Run: <code>{meta.install_hint}</code></Alert>
          )}

          <FormControlLabel
            control={<Checkbox checked={useRawUrl} onChange={(e) => setUseRawUrl(e.target.checked)} />}
            label="Paste a raw SQLAlchemy URL instead" />

          {renderEngineFields()}

          <Button variant="contained" onClick={buildAndConnect} disabled={busy || !meta?.driver_installed}>
            Connect
          </Button>

          {busy && <LinearProgress />}
          {err && <Alert severity="error">{err}</Alert>}
          {msg && <Alert severity="success">{msg}</Alert>}

          {tables.length > 0 && (
            <Stack spacing={1.5}>
              <TextField select size="small" label="Table"
                value={tablePick} onChange={(e) => setTablePick(e.target.value)}>
                {tables.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
              </TextField>
              <TextField multiline rows={3} size="small"
                label="Or enter a custom SQL query"
                value={customQuery} onChange={(e) => setCustomQuery(e.target.value)} />
              <Button variant="outlined" onClick={loadTable} disabled={busy}>
                Load Table
              </Button>
            </Stack>
          )}
        </Stack>
      </AccordionDetails>
    </Accordion>
  );
}
