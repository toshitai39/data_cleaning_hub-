import { useState } from 'react';
import {
  Box, Grid, Stack, Typography, Button, Alert, LinearProgress,
} from '@mui/material';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import api from '../api.js';
import PageHeader from '../components/PageHeader.jsx';
import ContentCard from '../components/ContentCard.jsx';
import { useDataset } from '../context/DatasetContext.jsx';
import HeaderConfigurator from './loaddata/HeaderConfigurator.jsx';
import DataStatus from './loaddata/DataStatus.jsx';
import DbConnector from './loaddata/DbConnector.jsx';
import NetSuiteConnector from './loaddata/NetSuiteConnector.jsx';
import ProjectTables from './loaddata/ProjectTables.jsx';

const FORMATS = [
  'CSV / TSV / TXT',
  'Excel (XLSX / XLS)',
  'JSON / JSONL',
  'Parquet',
  'Feather',
];

export default function LoadData() {
  const { state, refresh } = useDataset();
  const [staged, setStaged] = useState(null);
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
    } catch (e2) {
      setErr(e2?.response?.data?.detail || 'Upload failed');
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
      <PageHeader
        title="Load data"
        subtitle="Upload a dataset or connect a database. The pipeline runs on the active file until you reset or load a different one."
      />

      {/* NetSuite live-connector panel — credential form + stream loader.
          Renders only when the active project's system is NetSuite. */}
      <NetSuiteConnector onLoaded={handleLoaded} />

      {/* Multi-table upload panel — only renders for projects whose
          system has a real multi-table schema (SAP today). For file_upload
          and live-connector projects this component returns null. */}
      <ProjectTables />

      {!state.loaded && (
        <ContentCard sx={{ mb: 2.5 }}>
          <Grid container spacing={2.5}>
            <Grid item xs={12} md={8}>
              <Box
                sx={{
                  border: '2px dashed #DDD6E5',
                  borderRadius: 1.5,
                  bgcolor: '#F7F5FA',
                  px: 3,
                  py: 5,
                  textAlign: 'center',
                  transition: 'border-color 120ms, background-color 120ms',
                  '&:hover': { borderColor: '#6A28A8', bgcolor: '#F4ECF9' },
                }}
              >
                <CloudUploadIcon sx={{ fontSize: 44, color: '#6A28A8', mb: 1.25 }} />
                <Typography
                  sx={{
                    fontFamily: "'Montserrat', sans-serif",
                    fontWeight: 700,
                    fontSize: 17,
                    color: '#1A1A1A',
                    mb: 0.5,
                  }}
                >
                  Drag &amp; drop a master-data file
                </Typography>
                <Typography sx={{ fontSize: 13, color: '#8A8A8A', mb: 2 }}>
                  Or browse — up to 1 GB per file
                </Typography>
                <Button variant="contained" component="label" disabled={busy} size="large">
                  Choose file
                  <input
                    hidden
                    type="file"
                    accept=".csv,.tsv,.txt,.xlsx,.xls,.json,.jsonl,.parquet,.pq,.feather,.ftr"
                    onChange={onFile}
                  />
                </Button>
                {busy && (
                  <Box sx={{ mt: 2.5 }}>
                    <LinearProgress
                      variant={progress > 0 && progress < 100 ? 'determinate' : 'indeterminate'}
                      value={progress}
                    />
                    <Typography sx={{ fontSize: 12, color: '#8A8A8A', mt: 0.5 }}>
                      {statusText} {progress > 0 && progress < 100 ? `(${progress}%)` : ''}
                    </Typography>
                  </Box>
                )}
              </Box>
            </Grid>
            <Grid item xs={12} md={4}>
              <Box
                sx={{
                  border: '1px solid #E7E6E6',
                  borderRadius: 1.5,
                  bgcolor: '#FBFAFC',
                  p: 2.25,
                  height: '100%',
                }}
              >
                <Typography
                  sx={{
                    fontFamily: "'Montserrat', sans-serif",
                    fontSize: 11,
                    fontWeight: 700,
                    letterSpacing: '0.1em',
                    color: '#8A8A8A',
                    textTransform: 'uppercase',
                    mb: 1.25,
                  }}
                >
                  Supported formats
                </Typography>
                <Stack spacing={0.75}>
                  {FORMATS.map((f) => (
                    <Box key={f} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Box
                        sx={{
                          width: 5,
                          height: 5,
                          borderRadius: '50%',
                          bgcolor: '#6A28A8',
                        }}
                      />
                      <Typography sx={{ fontSize: 13, color: '#555555' }}>{f}</Typography>
                    </Box>
                  ))}
                </Stack>
              </Box>
            </Grid>
          </Grid>

          {err && <Alert severity="error" sx={{ mt: 2.5 }}>{err}</Alert>}

          {staged && (
            <Box sx={{ mt: 2.5 }}>
              <HeaderConfigurator stagedFile={staged} onLoaded={handleLoaded} />
            </Box>
          )}
        </ContentCard>
      )}

      {state.loaded && (
        <DataStatus
          filename={state.filename}
          onClearAll={handleClearAll}
          onLoadDifferent={handleLoadDifferent}
        />
      )}

      <DbConnector onLoaded={handleLoaded} />
    </>
  );
}
