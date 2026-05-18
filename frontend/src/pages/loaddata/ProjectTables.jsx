import { useEffect, useState } from 'react';
import {
  Box, Stack, Typography, Button, Chip, Alert, LinearProgress, IconButton,
  Tooltip,
} from '@mui/material';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import CloudUploadOutlinedIcon from '@mui/icons-material/CloudUploadOutlined';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import LinkOutlinedIcon from '@mui/icons-material/LinkOutlined';
import api from '../../api.js';
import ContentCard from '../../components/ContentCard.jsx';
import { useProject } from '../../context/ProjectContext.jsx';
import { useDataset } from '../../context/DatasetContext.jsx';

const SUPPORTED = '.csv,.tsv,.txt,.xlsx,.xls,.json,.jsonl,.parquet,.pq,.feather,.ftr';

function TableTile({ spec, meta, onUpload, onDelete, busy }) {
  const isUploaded = !!meta;
  const role = spec.role || 'primary';
  return (
    <Box
      sx={{
        position: 'relative',
        border: '1.5px solid',
        borderColor: isUploaded ? '#2F8F57' : (spec.required ? '#DDD6E5' : '#E7E6E6'),
        bgcolor: isUploaded ? '#F4FAF6' : '#FBFAFC',
        borderRadius: 1.5,
        p: 2,
        minHeight: 130,
        // ``minWidth: 0`` lets this Box shrink below its content's natural
        // width inside a grid track — without it, long descriptions force
        // the column wider than its 1fr share and adjacent tiles overflow.
        minWidth: 0,
        display: 'flex',
        flexDirection: 'column',
        gap: 1,
      }}
    >
      <Stack direction="row" alignItems="flex-start" justifyContent="space-between" spacing={1}>
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Stack direction="row" spacing={0.75} alignItems="center">
            <Typography
              sx={{
                fontFamily: 'ui-monospace, Menlo, monospace',
                fontSize: 13.5,
                fontWeight: 700,
                color: '#6A28A8',
              }}
            >
              {spec.id}
            </Typography>
            <Chip
              size="small"
              label={role}
              variant="outlined"
              sx={{ height: 18, fontSize: '0.65rem' }}
            />
            {spec.required ? (
              <Chip size="small" label="required" sx={{ height: 18, fontSize: '0.65rem', bgcolor: '#FBEAEA', color: '#D14343' }} />
            ) : (
              <Chip size="small" label="optional" sx={{ height: 18, fontSize: '0.65rem', bgcolor: '#F1ECF6', color: '#8A8A8A' }} />
            )}
          </Stack>
          <Typography sx={{ fontSize: 13, fontWeight: 600, color: '#1A1A1A', mt: 0.5 }}>
            {spec.label}
          </Typography>
          <Typography
            sx={{
              fontSize: 11.5,
              color: '#8A8A8A',
              lineHeight: 1.4,
              // Clamp to two lines so tall descriptions don't make some
              // tiles taller than others. Long text gets an ellipsis.
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }}
            title={spec.description}
          >
            {spec.description}
          </Typography>
        </Box>
        {isUploaded && (
          <Tooltip title="Remove this table">
            <IconButton size="small" onClick={() => onDelete(spec.id)} disabled={busy}>
              <DeleteOutlineIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
      </Stack>

      {isUploaded ? (
        <Stack direction="row" alignItems="center" spacing={1}>
          <CheckCircleOutlineIcon sx={{ color: '#2F8F57', fontSize: 18 }} />
          <Typography sx={{ fontSize: 12, color: '#2F8F57', fontWeight: 600 }}>
            {meta.rows?.toLocaleString()} rows · {meta.columns} cols
          </Typography>
        </Stack>
      ) : (
        <Box sx={{ mt: 'auto' }}>
          <Button
            component="label"
            size="small"
            variant="outlined"
            fullWidth
            startIcon={<CloudUploadOutlinedIcon />}
            disabled={busy}
          >
            Upload {spec.id}
            <input
              hidden
              type="file"
              accept={SUPPORTED}
              onChange={(e) => {
                const f = e.target.files?.[0];
                e.target.value = '';
                if (f) onUpload(spec.id, f);
              }}
            />
          </Button>
        </Box>
      )}

      {spec.join_key && (
        <Typography sx={{ fontSize: 10.5, color: '#8A8A8A', mt: 0.5 }}>
          joins on <Box component="code" sx={{ bgcolor: '#F4ECF9', px: 0.5, borderRadius: 0.5, color: '#6A28A8' }}>{spec.join_key}</Box>
        </Typography>
      )}
    </Box>
  );
}

export default function ProjectTables() {
  const { active, refresh: refreshProjects } = useProject();
  const { refresh: refreshDataset } = useDataset();
  const [tables, setTables] = useState({ expected: [], org_setup_tables: [], uploaded: {}, missing_required: [] });
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Multi-table file-upload flow is for systems where the user supplies
  // each table as a separate file (SAP today). Live API connectors like
  // NetSuite have their own dedicated panel — don't double-render the
  // upload tiles for them.
  const isMultiTable =
    active && !['file_upload', 'netsuite'].includes(active.system?.id);

  const load = async () => {
    if (!active) return;
    setLoading(true);
    setError('');
    try {
      const { data } = await api.get(`/projects/${active.id}/tables`);
      setTables(data);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not load table schema');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { if (isMultiTable) load(); }, [active?.id, isMultiTable]);

  const upload = async (tableId, file) => {
    setBusy(true); setError(''); setSuccess('');
    try {
      const fd = new FormData();
      fd.append('file', file);
      await api.post(`/projects/${active.id}/tables/${tableId}/upload`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      await load();
    } catch (e) {
      setError(e?.response?.data?.detail || `Upload failed for ${tableId}`);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (tableId) => {
    if (!window.confirm(`Remove ${tableId}? You'll need to re-upload it.`)) return;
    setBusy(true); setError(''); setSuccess('');
    try {
      await api.delete(`/projects/${active.id}/tables/${tableId}`);
      await load();
    } catch (e) {
      setError(e?.response?.data?.detail || `Delete failed for ${tableId}`);
    } finally {
      setBusy(false);
    }
  };

  const materialize = async () => {
    setBusy(true); setError(''); setSuccess('');
    try {
      const { data } = await api.post(`/projects/${active.id}/materialize`);
      setSuccess(
        `Working dataset built: ${data.rows.toLocaleString()} rows × ${data.columns} columns ` +
        `(joined ${data.extensions_applied.length} extension table${data.extensions_applied.length === 1 ? '' : 's'}).`,
      );
      await Promise.all([refreshProjects(), refreshDataset()]);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Materialize failed');
    } finally {
      setBusy(false);
    }
  };

  if (!isMultiTable) return null;

  const canMaterialize =
    tables.missing_required.length === 0 &&
    Object.keys(tables.uploaded || {}).length > 0;

  return (
    <ContentCard sx={{ mb: 2.5, p: 2.5 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }}>
        <Box>
          <Stack direction="row" spacing={1} alignItems="center">
            <LinkOutlinedIcon sx={{ color: '#6A28A8' }} />
            <Typography
              sx={{
                fontFamily: "'Montserrat', sans-serif",
                fontSize: 17,
                fontWeight: 700,
                color: '#1A1A1A',
              }}
            >
              Tables for {active.stream?.label}
            </Typography>
            <Chip
              size="small"
              label={active.system?.label}
              sx={{ height: 20, fontSize: '0.7rem', bgcolor: '#F4ECF9', color: '#6A28A8' }}
            />
          </Stack>
          <Typography sx={{ fontSize: 12.5, color: '#555555', mt: 0.5 }}>
            Upload each physical table this stream uses. The primary table is the spine;
            extensions are joined onto it on their declared key.
          </Typography>
        </Box>
        <Button
          variant="contained"
          onClick={materialize}
          disabled={busy || !canMaterialize}
          sx={{ py: 1.1, px: 2.5, fontWeight: 700, minWidth: 180 }}
        >
          {busy ? 'Building…' : 'Build working dataset'}
        </Button>
      </Stack>

      {loading && <LinearProgress sx={{ mb: 1.5 }} />}
      {error && <Alert severity="error" sx={{ mb: 1.5 }}>{typeof error === 'string' ? error : JSON.stringify(error)}</Alert>}
      {success && <Alert severity="success" sx={{ mb: 1.5 }}>{success}</Alert>}
      {tables.missing_required?.length > 0 && (
        <Alert severity="warning" sx={{ mb: 1.5 }}>
          Required table{tables.missing_required.length === 1 ? '' : 's'} missing:
          {' '}
          <b>{tables.missing_required.join(', ')}</b>
        </Alert>
      )}

      <Box
        sx={{
          display: 'grid',
          // auto-fit lets the browser decide how many 280-px tiles fit
          // in the available content width — so 1 / 2 / 3 columns adapt
          // to the actual viewport instead of hard-coding a breakpoint.
          gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
          gap: 1.5,
        }}
      >
        {(tables.expected || []).map((spec) => (
          <TableTile
            key={spec.id}
            spec={spec}
            meta={tables.uploaded?.[spec.id]}
            onUpload={upload}
            onDelete={remove}
            busy={busy}
          />
        ))}
      </Box>

      {tables.org_setup_tables?.length > 0 && (
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
            Organisation setup tables ({active.system?.label})
          </Typography>
          <Typography sx={{ fontSize: 12, color: '#8A8A8A', mb: 1 }}>
            Shared reference data — usually loaded once per ERP and reused across projects.
            Coming soon as a shared upload area.
          </Typography>
          <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
            {tables.org_setup_tables.map((t) => (
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
    </ContentCard>
  );
}
