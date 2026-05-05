import { useEffect, useState } from 'react';
import {
  Box, Grid, Paper, Stack, Typography, Button, Alert, LinearProgress, Chip,
} from '@mui/material';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import api from '../api.js';
import PageHeader from '../components/PageHeader.jsx';
import { useDataset } from '../context/DatasetContext.jsx';
import HeaderConfigurator from './loaddata/HeaderConfigurator.jsx';
import DataStatus from './loaddata/DataStatus.jsx';
import DbConnector from './loaddata/DbConnector.jsx';

export default function LoadData() {
  const { state, refresh } = useDataset();
  const [staged, setStaged] = useState(null);   // raw upload (file_path, sheets, file_type)
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState('');

  const onFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true); setErr(''); setStaged(null); setProgress(0);
    setStatusText(`Uploading ${file.name}…`);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const { data } = await api.post('/data/upload-raw', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (ev) => {
          if (ev.total) setProgress(Math.round((ev.loaded / ev.total) * 100));
        },
      });
      setStatusText('Reading file…');
      setStaged(data);
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Upload failed');
    } finally {
      setBusy(false); setStatusText('');
    }
    e.target.value = '';
  };

  const handleLoaded = async () => {
    setStaged(null);
    await refresh();
  };

  const handleLoadDifferent = async () => {
    await api.post('/data/clear');
    setStaged(null);
    await refresh();
  };

  const handleClearAll = async () => {
    await api.post('/data/clear');
    setStaged(null);
    await refresh();
  };

  return (
    <>
      <PageHeader title="Load Data (Up to 1 GB)" />

      {/* File upload card */}
      {!state.loaded && (
        <Paper sx={{ p: 3, mb: 2 }}>
          <Grid container spacing={2}>
            <Grid item xs={12} md={9}>
              <Box sx={{
                border: '2px dashed', borderColor: 'divider', borderRadius: 2,
                p: 4, textAlign: 'center', bgcolor: '#f8fafc',
              }}>
                <CloudUploadIcon sx={{ fontSize: 40, color: 'primary.light', mb: 1 }} />
                <Typography variant="subtitle1" sx={{ mb: 0.5 }}>Choose a file</Typography>
                <Typography variant="caption" color="text.secondary">
                  Supports files up to 1 GB
                </Typography>
                <Box sx={{ mt: 2 }}>
                  <Button variant="contained" component="label" disabled={busy}>
                    Select File
                    <input hidden type="file"
                      accept=".csv,.tsv,.txt,.xlsx,.xls,.json,.jsonl,.parquet,.pq,.feather,.ftr"
                      onChange={onFile} />
                  </Button>
                </Box>
                {busy && (
                  <Box sx={{ mt: 2 }}>
                    <LinearProgress variant={progress > 0 && progress < 100 ? 'determinate' : 'indeterminate'} value={progress} />
                    <Typography variant="caption" color="text.secondary">
                      {statusText} {progress > 0 && progress < 100 ? ` (${progress}%)` : ''}
                    </Typography>
                  </Box>
                )}
              </Box>
            </Grid>
            <Grid item xs={12} md={3}>
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Typography variant="subtitle2" gutterBottom>Supported Formats</Typography>
                <Stack spacing={0.25}>
                  <Typography variant="caption">• CSV/TSV/TXT</Typography>
                  <Typography variant="caption">• Excel (XLSX/XLS)</Typography>
                  <Typography variant="caption">• JSON/JSONL</Typography>
                  <Typography variant="caption">• Parquet</Typography>
                  <Typography variant="caption">• Feather</Typography>
                </Stack>
              </Paper>
            </Grid>
          </Grid>

          {err && <Alert severity="error" sx={{ mt: 2 }}>{err}</Alert>}

          {staged && (
            <HeaderConfigurator stagedFile={staged} onLoaded={handleLoaded} />
          )}
        </Paper>
      )}

      {/* Loaded data status */}
      {state.loaded && (
        <Paper sx={{ p: 3, mb: 2 }}>
          <DataStatus filename={state.filename}
            onClearAll={handleClearAll}
            onLoadDifferent={handleLoadDifferent} />
        </Paper>
      )}

      {/* Database connector */}
      <DbConnector onLoaded={handleLoaded} />
    </>
  );
}
