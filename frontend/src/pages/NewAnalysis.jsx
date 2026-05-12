import { useEffect, useState } from 'react';
import {
  Box, Grid, Typography, Button, Stack, Chip, TextField, Alert, LinearProgress,
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import StorageOutlinedIcon from '@mui/icons-material/StorageOutlined';
import CloudUploadOutlinedIcon from '@mui/icons-material/CloudUploadOutlined';
import AltRouteOutlinedIcon from '@mui/icons-material/AltRouteOutlined';
import api from '../api.js';
import { useProject } from '../context/ProjectContext.jsx';

const SYSTEM_ICON = {
  file_upload: CloudUploadOutlinedIcon,
};

function StepLabel({ index, label, active, done }) {
  return (
    <Stack direction="row" alignItems="center" spacing={1.25}>
      <Box
        sx={{
          width: 28,
          height: 28,
          borderRadius: '50%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: "'Montserrat', sans-serif",
          fontSize: 13,
          fontWeight: 700,
          bgcolor: done ? '#2F8F57' : active ? '#6A28A8' : '#F1ECF6',
          color: done || active ? '#FFFFFF' : '#8A8A8A',
          transition: 'background-color 120ms',
        }}
      >
        {done ? '✓' : index}
      </Box>
      <Typography
        sx={{
          fontFamily: "'Montserrat', sans-serif",
          fontSize: 13,
          fontWeight: active || done ? 700 : 500,
          color: active ? '#6A28A8' : done ? '#2F8F57' : '#8A8A8A',
          letterSpacing: '0.04em',
          textTransform: 'uppercase',
        }}
      >
        {label}
      </Typography>
    </Stack>
  );
}

function PickCard({ icon: Icon, label, description, selected, disabled, onClick }) {
  return (
    <Box
      role="button"
      aria-disabled={disabled}
      onClick={disabled ? undefined : onClick}
      sx={{
        position: 'relative',
        bgcolor: selected ? '#F4ECF9' : '#FFFFFF',
        border: '1.5px solid',
        borderColor: selected ? '#6A28A8' : '#E7E6E6',
        borderRadius: 1.5,
        p: 2.25,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.55 : 1,
        transition: 'border-color 120ms, background-color 120ms, transform 120ms',
        '&:hover': disabled ? {} : {
          borderColor: '#6A28A8',
          transform: 'translateY(-1px)',
        },
      }}
    >
      {selected && (
        <CheckCircleOutlineIcon
          sx={{
            position: 'absolute',
            top: 12,
            right: 12,
            color: '#6A28A8',
            fontSize: 20,
          }}
        />
      )}
      <Box
        sx={{
          width: 44,
          height: 44,
          borderRadius: 1.25,
          bgcolor: selected ? '#FFFFFF' : '#F4ECF9',
          color: '#6A28A8',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          mb: 1.25,
        }}
      >
        {Icon && <Icon sx={{ fontSize: 22 }} />}
      </Box>
      <Typography
        sx={{
          fontFamily: "'Montserrat', sans-serif",
          fontSize: 15,
          fontWeight: 700,
          color: '#1A1A1A',
          mb: 0.5,
        }}
      >
        {label}
      </Typography>
      <Typography sx={{ fontSize: 12.5, color: '#555555', lineHeight: 1.4 }}>
        {description}
      </Typography>
      {disabled && (
        <Chip
          size="small"
          label="Coming soon"
          sx={{ mt: 1, height: 20, fontSize: '0.7rem', bgcolor: '#F1ECF6', color: '#8A8A8A' }}
        />
      )}
    </Box>
  );
}

export default function NewAnalysis({ onCancel, onCreated }) {
  const { setActive, refresh } = useProject();
  const [catalog, setCatalog] = useState({ systems: [], streams: [] });
  const [schema, setSchema] = useState(null);
  const [systemId, setSystemId] = useState('');
  const [streamId, setStreamId] = useState('');
  const [name, setName] = useState('');
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    api.get('/projects/catalog').then(({ data }) => setCatalog(data)).catch(() => {});
  }, []);

  // Fetch the table schema for the picked (system, stream) once we have
  // both — so the Confirm step can show "this stream expects N tables".
  useEffect(() => {
    if (!systemId || !streamId) { setSchema(null); return; }
    api
      .get('/projects/catalog/schema', { params: { system_id: systemId, stream_id: streamId } })
      .then(({ data }) => setSchema(data))
      .catch(() => setSchema(null));
  }, [systemId, streamId]);

  const selectedSystem = catalog.systems.find((s) => s.id === systemId);
  const selectedStream = catalog.streams.find((s) => s.id === streamId);

  const canNextStep1 = !!systemId && selectedSystem?.status === 'available';
  const canNextStep2 = !!streamId;

  const defaultName = () => {
    if (!selectedSystem || !selectedStream) return '';
    const date = new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
    return `${selectedSystem.label} · ${selectedStream.label} · ${date}`;
  };

  const create = async () => {
    if (!canNextStep1 || !canNextStep2) return;
    setBusy(true);
    setError('');
    try {
      const { data } = await api.post('/projects', {
        system_id: systemId,
        stream_id: streamId,
        name: name.trim() || null,
      });
      await refresh();
      await setActive(data);
      if (onCreated) onCreated(data);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not create project');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
        <Typography
          sx={{
            fontFamily: "'Montserrat', sans-serif",
            fontSize: { xs: 28, md: 34 },
            fontWeight: 800,
            color: '#1A1A1A',
            letterSpacing: '-0.02em',
          }}
        >
          New analysis
        </Typography>
        <Button
          variant="outlined"
          startIcon={<ArrowBackIcon />}
          onClick={onCancel}
          sx={{ borderColor: '#E7E6E6', color: '#555555' }}
        >
          Cancel
        </Button>
      </Stack>
      <Typography sx={{ fontSize: 14, color: '#555555', mb: 3 }}>
        Pick a source system and the master-data stream you want to clean. You can run multiple streams in parallel — each one is its own project.
      </Typography>

      {/* Step indicators */}
      <Stack
        direction="row"
        spacing={3}
        sx={{
          pb: 2.5,
          borderBottom: '1px solid #E7E6E6',
          mb: 3,
        }}
      >
        <StepLabel index={1} label="Source system" active={step === 1} done={step > 1} />
        <StepLabel index={2} label="Master-data stream" active={step === 2} done={step > 2} />
        <StepLabel index={3} label="Confirm" active={step === 3} done={false} />
      </Stack>

      {busy && <LinearProgress sx={{ mb: 2 }} />}
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {step === 1 && (
        <>
          <Typography
            sx={{
              fontFamily: "'Montserrat', sans-serif",
              fontSize: 18,
              fontWeight: 700,
              color: '#1A1A1A',
              mb: 2,
            }}
          >
            Choose a source system
          </Typography>
          <Grid container spacing={1.75}>
            {catalog.systems.map((s) => (
              <Grid item xs={12} sm={6} md={4} key={s.id}>
                <PickCard
                  icon={SYSTEM_ICON[s.id] || StorageOutlinedIcon}
                  label={s.label}
                  description={s.description}
                  selected={systemId === s.id}
                  disabled={s.status !== 'available'}
                  onClick={() => setSystemId(s.id)}
                />
              </Grid>
            ))}
          </Grid>
          <Stack direction="row" justifyContent="flex-end" sx={{ mt: 3 }}>
            <Button
              variant="contained"
              endIcon={<ArrowForwardIcon />}
              disabled={!canNextStep1}
              onClick={() => setStep(2)}
              sx={{ py: 1.25, px: 2.5, fontWeight: 700 }}
            >
              Continue
            </Button>
          </Stack>
        </>
      )}

      {step === 2 && (
        <>
          <Typography
            sx={{
              fontFamily: "'Montserrat', sans-serif",
              fontSize: 18,
              fontWeight: 700,
              color: '#1A1A1A',
              mb: 2,
            }}
          >
            Choose a master-data stream
          </Typography>
          <Grid container spacing={1.75}>
            {catalog.streams.map((s) => (
              <Grid item xs={12} sm={6} md={4} key={s.id}>
                <PickCard
                  icon={AltRouteOutlinedIcon}
                  label={s.label}
                  description={s.description}
                  selected={streamId === s.id}
                  onClick={() => setStreamId(s.id)}
                />
              </Grid>
            ))}
          </Grid>
          <Stack direction="row" justifyContent="space-between" sx={{ mt: 3 }}>
            <Button
              variant="outlined"
              startIcon={<ArrowBackIcon />}
              onClick={() => setStep(1)}
              sx={{ borderColor: '#E7E6E6', color: '#555555' }}
            >
              Back
            </Button>
            <Button
              variant="contained"
              endIcon={<ArrowForwardIcon />}
              disabled={!canNextStep2}
              onClick={() => { setName(defaultName()); setStep(3); }}
              sx={{ py: 1.25, px: 2.5, fontWeight: 700 }}
            >
              Continue
            </Button>
          </Stack>
        </>
      )}

      {step === 3 && (
        <>
          <Typography
            sx={{
              fontFamily: "'Montserrat', sans-serif",
              fontSize: 18,
              fontWeight: 700,
              color: '#1A1A1A',
              mb: 2,
            }}
          >
            Confirm your analysis
          </Typography>

          <Box
            sx={{
              bgcolor: '#FBFAFC',
              border: '1px solid #E7E6E6',
              borderRadius: 1.5,
              p: 2.5,
              mb: 2.5,
            }}
          >
            <Stack direction="row" spacing={3} sx={{ mb: 2 }}>
              <Box>
                <Typography sx={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '0.1em', color: '#8A8A8A', textTransform: 'uppercase' }}>
                  Source system
                </Typography>
                <Typography sx={{ fontFamily: "'Montserrat', sans-serif", fontSize: 15, fontWeight: 700, color: '#1A1A1A' }}>
                  {selectedSystem?.label}
                </Typography>
              </Box>
              <Box>
                <Typography sx={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '0.1em', color: '#8A8A8A', textTransform: 'uppercase' }}>
                  Master-data stream
                </Typography>
                <Typography sx={{ fontFamily: "'Montserrat', sans-serif", fontSize: 15, fontWeight: 700, color: '#1A1A1A' }}>
                  {selectedStream?.label}
                </Typography>
              </Box>
            </Stack>
            <TextField
              label="Project name"
              fullWidth
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={defaultName()}
              helperText="You can rename later from the Home page."
            />
          </Box>

          {/* Schema preview — only meaningful for systems with a real
              multi-table schema (SAP today). File-upload streams collapse
              to a single primary table so the panel adds no value. */}
          {schema && schema.tables && schema.tables.length > 1 && (
            <Box
              sx={{
                border: '1px solid #E7E6E6',
                borderRadius: 1.5,
                p: 2.5,
                mb: 2.5,
              }}
            >
              <Typography
                sx={{
                  fontFamily: "'Montserrat', sans-serif",
                  fontSize: 15,
                  fontWeight: 700,
                  color: '#1A1A1A',
                  mb: 1,
                }}
              >
                Tables this stream uses
              </Typography>
              <Typography sx={{ fontSize: 12.5, color: '#555555', mb: 1.5 }}>
                {selectedSystem?.label} stores {selectedStream?.label?.toLowerCase()} data
                across these physical tables. After creating the project you'll
                upload each one separately.
              </Typography>
              <Stack spacing={0.75}>
                {schema.tables.map((t) => (
                  <Stack
                    key={t.id}
                    direction="row"
                    spacing={1.5}
                    alignItems="center"
                    sx={{
                      px: 1.5,
                      py: 1,
                      bgcolor: '#FBFAFC',
                      border: '1px solid #E7E6E6',
                      borderRadius: 1,
                    }}
                  >
                    <Typography
                      sx={{
                        fontFamily: 'ui-monospace, Menlo, monospace',
                        fontSize: 12,
                        fontWeight: 700,
                        color: '#6A28A8',
                        minWidth: 64,
                      }}
                    >
                      {t.id}
                    </Typography>
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography sx={{ fontSize: 13, fontWeight: 600, color: '#1A1A1A' }}>
                        {t.label}
                      </Typography>
                      <Typography sx={{ fontSize: 11.5, color: '#8A8A8A' }} noWrap>
                        {t.description}
                      </Typography>
                    </Box>
                    <Chip
                      size="small"
                      label={t.required ? 'required' : 'optional'}
                      sx={{
                        height: 20,
                        fontSize: '0.68rem',
                        fontWeight: 700,
                        bgcolor: t.required ? '#FBEAEA' : '#F1ECF6',
                        color: t.required ? '#D14343' : '#8A8A8A',
                      }}
                    />
                    <Chip
                      size="small"
                      variant="outlined"
                      label={t.role}
                      sx={{ height: 20, fontSize: '0.68rem' }}
                    />
                  </Stack>
                ))}
              </Stack>

              {schema.org_setup_tables && schema.org_setup_tables.length > 0 && (
                <Box sx={{ mt: 2.5 }}>
                  <Typography
                    sx={{
                      fontSize: 11,
                      fontWeight: 700,
                      letterSpacing: '0.1em',
                      color: '#8A8A8A',
                      textTransform: 'uppercase',
                      mb: 0.75,
                    }}
                  >
                    Plus organisation setup tables (one-time per ERP)
                  </Typography>
                  <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                    {schema.org_setup_tables.map((t) => (
                      <Chip
                        key={t.id}
                        size="small"
                        label={`${t.id} — ${t.label}`}
                        title={t.description}
                        sx={{
                          height: 22,
                          fontSize: '0.72rem',
                          bgcolor: '#F4ECF9',
                          color: '#6A28A8',
                          fontFamily: 'ui-monospace, Menlo, monospace',
                        }}
                      />
                    ))}
                  </Stack>
                </Box>
              )}
            </Box>
          )}

          <Stack direction="row" justifyContent="space-between">
            <Button
              variant="outlined"
              startIcon={<ArrowBackIcon />}
              onClick={() => setStep(2)}
              sx={{ borderColor: '#E7E6E6', color: '#555555' }}
            >
              Back
            </Button>
            <Button
              variant="contained"
              onClick={create}
              disabled={busy}
              sx={{ py: 1.25, px: 3, fontWeight: 700 }}
            >
              {busy ? 'Creating…' : 'Create analysis'}
            </Button>
          </Stack>
        </>
      )}
    </Box>
  );
}
