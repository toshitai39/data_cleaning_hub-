import { useEffect, useMemo, useState } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions, Button, Box, Typography,
  Chip, IconButton, TextField, Alert, LinearProgress, Stack, Tooltip,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import RestartAltOutlinedIcon from '@mui/icons-material/RestartAltOutlined';
import api from '../../api.js';

function fmt(v) {
  if (v == null || v === '') return '—';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

export default function GoldenRecordDialog({
  open,
  onClose,
  dup_type,
  group_id,
  rule_id,
  onApplied,
}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [overrides, setOverrides] = useState({});
  const [editingCol, setEditingCol] = useState(null);

  useEffect(() => {
    if (!open || !dup_type || group_id == null) return;
    setLoading(true);
    setError('');
    setOverrides({});
    setEditingCol(null);
    api
      .get(`/duplicates/${dup_type}/group/${group_id}/golden`, {
        params: rule_id ? { rule_id } : {},
      })
      .then(({ data }) => setData(data))
      .catch((e) => setError(e?.response?.data?.detail || 'Could not load group'))
      .finally(() => setLoading(false));
  }, [open, dup_type, group_id, rule_id]);

  const columns = useMemo(() => {
    if (!data?.members?.[0]?.values) return [];
    return Object.keys(data.members[0].values);
  }, [data]);

  const goldenValue = (col) => {
    if (col in overrides) return overrides[col];
    return data?.golden_record?.[col];
  };

  const setOverride = (col, val) => {
    setOverrides((o) => ({ ...o, [col]: val }));
  };

  const clearOverride = (col) => {
    setOverrides((o) => {
      const next = { ...o };
      delete next[col];
      return next;
    });
  };

  const apply = async () => {
    setApplying(true);
    setError('');
    try {
      await api.post(`/duplicates/${dup_type}/group/${group_id}/apply-golden`, {
        rule_id: rule_id || null,
        overrides: Object.keys(overrides).length ? overrides : null,
      });
      if (onApplied) onApplied();
    } catch (e) {
      setError(e?.response?.data?.detail || 'Apply failed');
    } finally {
      setApplying(false);
    }
  };

  return (
    <Dialog open={!!open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
        <Box>
          <Typography sx={{ fontFamily: "'Montserrat', sans-serif", fontWeight: 700, fontSize: 18 }}>
            Golden record · Group #{group_id}
          </Typography>
          {data?.survivorship_strategy && (
            <Typography sx={{ fontSize: 12, color: '#8A8A8A' }}>
              Survivorship strategy: <b>{data.survivorship_strategy}</b>
              {rule_id && ` · from rule ${rule_id}`}
            </Typography>
          )}
        </Box>
        <Box sx={{ flex: 1 }} />
        <IconButton onClick={onClose} disabled={applying}>
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        {loading && <LinearProgress sx={{ mb: 2 }} />}
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        {data && (
          <>
            <Alert severity="info" sx={{ mb: 2 }}>
              The survivor row is highlighted. Each column's golden value comes from the
              source row marked in <i>Provenance</i>. Click <EditOutlinedIcon sx={{ fontSize: 13, verticalAlign: 'middle' }} />
              to override a value before applying.
            </Alert>

            <TableContainer component={Paper} variant="outlined">
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 700, position: 'sticky', left: 0, bgcolor: '#FBFAFC', zIndex: 2 }}>
                      Critical data element
                    </TableCell>
                    {data.members.map((m) => (
                      <TableCell
                        key={m.index}
                        sx={{
                          fontWeight: 700,
                          minWidth: 160,
                          bgcolor: m.is_survivor ? '#F4ECF9' : '#FBFAFC',
                          color: m.is_survivor ? '#6A28A8' : '#555555',
                        }}
                      >
                        Row {m.index}
                        {m.is_survivor && (
                          <Chip
                            size="small"
                            label="survivor"
                            sx={{ ml: 1, height: 18, fontSize: '0.65rem', bgcolor: '#6A28A8', color: 'white' }}
                          />
                        )}
                      </TableCell>
                    ))}
                    <TableCell sx={{ fontWeight: 700, minWidth: 200, bgcolor: '#E8F4ED', color: '#14532D' }}>
                      Golden record
                    </TableCell>
                    <TableCell sx={{ fontWeight: 700, width: 130 }}>Provenance</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {columns.map((col) => {
                    const prov = data.provenance?.[col] || {};
                    const isOverridden = col in overrides;
                    const golden = goldenValue(col);
                    return (
                      <TableRow key={col} hover>
                        <TableCell
                          sx={{
                            fontFamily: 'ui-monospace, Menlo, monospace',
                            fontSize: '0.78rem',
                            fontWeight: 600,
                            position: 'sticky',
                            left: 0,
                            bgcolor: '#FBFAFC',
                          }}
                        >
                          {col}
                        </TableCell>
                        {data.members.map((m) => {
                          const v = m.values?.[col];
                          const isContributor = prov.source_index === m.index;
                          return (
                            <TableCell
                              key={m.index}
                              sx={{
                                fontFamily: 'ui-monospace, Menlo, monospace',
                                fontSize: '0.78rem',
                                bgcolor: isContributor && !isOverridden ? '#E8F4ED' : 'transparent',
                                color: v == null || v === '' ? '#8A8A8A' : '#1A1A1A',
                                maxWidth: 220,
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap',
                              }}
                              title={fmt(v)}
                            >
                              {fmt(v)}
                            </TableCell>
                          );
                        })}
                        <TableCell sx={{ bgcolor: '#E8F4ED' }}>
                          {editingCol === col ? (
                            <Stack direction="row" spacing={0.5}>
                              <TextField
                                size="small"
                                autoFocus
                                value={golden ?? ''}
                                onChange={(e) => setOverride(col, e.target.value)}
                                sx={{ minWidth: 120 }}
                              />
                              <Button
                                size="small"
                                variant="contained"
                                onClick={() => setEditingCol(null)}
                              >
                                OK
                              </Button>
                            </Stack>
                          ) : (
                            <Stack direction="row" alignItems="center" spacing={0.75}>
                              <Typography
                                sx={{
                                  fontFamily: 'ui-monospace, Menlo, monospace',
                                  fontSize: '0.78rem',
                                  fontWeight: isOverridden ? 700 : 500,
                                  color: '#1A1A1A',
                                  flex: 1,
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  whiteSpace: 'nowrap',
                                }}
                                title={fmt(golden)}
                              >
                                {fmt(golden)}
                              </Typography>
                              <Tooltip title="Override this value">
                                <IconButton size="small" onClick={() => setEditingCol(col)}>
                                  <EditOutlinedIcon sx={{ fontSize: 15 }} />
                                </IconButton>
                              </Tooltip>
                              {isOverridden && (
                                <Tooltip title="Revert to computed value">
                                  <IconButton size="small" onClick={() => clearOverride(col)}>
                                    <RestartAltOutlinedIcon sx={{ fontSize: 15 }} />
                                  </IconButton>
                                </Tooltip>
                              )}
                            </Stack>
                          )}
                        </TableCell>
                        <TableCell>
                          {isOverridden ? (
                            <Chip
                              size="small"
                              label="manual"
                              sx={{ height: 20, fontSize: '0.7rem', bgcolor: '#FCF3E2', color: '#7A4F09' }}
                            />
                          ) : prov.source_index != null ? (
                            <Tooltip title={prov.reason || ''}>
                              <Chip
                                size="small"
                                label={`row ${prov.source_index}`}
                                sx={{ height: 20, fontSize: '0.7rem' }}
                                variant="outlined"
                              />
                            </Tooltip>
                          ) : (
                            <Chip
                              size="small"
                              label="all null"
                              variant="outlined"
                              sx={{ height: 20, fontSize: '0.7rem', color: '#8A8A8A' }}
                            />
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>

            {Object.keys(overrides).length > 0 && (
              <Alert severity="warning" icon={<EditOutlinedIcon />} sx={{ mt: 2 }}>
                <b>{Object.keys(overrides).length}</b> critical data element{Object.keys(overrides).length === 1 ? '' : 's'} manually overridden.
                Apply will use your edits in place of the computed values.
              </Alert>
            )}
          </>
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={onClose} disabled={applying}>Cancel</Button>
        <Button
          variant="contained"
          startIcon={<CheckCircleOutlineIcon />}
          onClick={apply}
          disabled={applying || !data}
        >
          {applying ? 'Applying…' : 'Apply golden record · drop duplicates'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
