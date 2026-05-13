import { useEffect, useState } from 'react';
import {
  Box, Paper, Typography, Stack, Button, Chip, LinearProgress, Alert, Snackbar,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Dialog, DialogTitle, DialogContent, DialogActions, IconButton,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import VisibilityIcon from '@mui/icons-material/Visibility';
import CloseIcon from '@mui/icons-material/Close';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import FilterAltOffOutlinedIcon from '@mui/icons-material/FilterAltOffOutlined';
import DownloadIcon from '@mui/icons-material/Download';
import api from '../../api.js';
import { useDataset } from '../../context/DatasetContext.jsx';

const FAMILY_LABEL = {
  composite_unique:      'Composite uniqueness',
  conditional_presence:  'Conditional presence',
  prefix_from_sibling:   'Prefix / contains',
  arithmetic:            'Arithmetic identity',
  llm:                   'AI-translated',
  manual:                'Manual review',
};

const FAMILY_COLOR = {
  composite_unique:      { bg: '#eff6ff', fg: '#1e40af' },
  conditional_presence:  { bg: '#fef3c7', fg: '#92400e' },
  prefix_from_sibling:   { bg: '#f0fdf4', fg: '#166534' },
  arithmetic:            { bg: '#faf5ff', fg: '#6b21a8' },
  llm:                   { bg: '#fff7ed', fg: '#c2410c' },
  manual:                { bg: '#f1f5f9', fg: '#475569' },
};

export default function CrossFieldPanel({ onAfterFix }) {
  const { refresh } = useDataset();
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(false);
  const [acting, setActing] = useState(false);
  const [err, setErr] = useState('');
  const [toast, setToast] = useState('');
  const [evaluated, setEvaluated] = useState(false);
  const [failingFor, setFailingFor] = useState(null); // { id, rule, columns, sample, family }

  const load = async () => {
    setLoading(true); setErr('');
    try {
      const { data } = await api.get('/quality/cross-field/rules');
      setRules(data.rules || []);
      setEvaluated(!!data.evaluated);
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Failed to load cross-field rules');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const viewFailing = async (rule) => {
    setLoading(true);
    try {
      const { data } = await api.get(`/quality/cross-field/failing-rows/${rule.id}`, {
        params: { limit: 50 },
      });
      setFailingFor({
        id: rule.id,
        rule: data.rule,
        expression: data.expression,
        family: data.family,
        count: data.count,
        columns: data.columns || [],
        sample: data.failing_sample || [],
      });
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Failed to load failing rows');
    } finally {
      setLoading(false);
    }
  };

  // ── Actions on the failing-rows dialog ───────────────────────────────
  const applyFix = async (action, ruleId, family, count) => {
    if (acting) return;
    const headline = action === 'deduplicate'
      ? 'Deduplicate this group of duplicate tuples?'
      : `Drop ${count} failing row${count === 1 ? '' : 's'} from the working dataset?`;
    const detail = action === 'deduplicate'
      ? 'For each duplicate tuple, the first occurrence is kept and the rest are dropped.'
      : 'These rows will be removed from the current working copy.';
    const tail = 'The original snapshot is preserved — you can reset from the Compare tab.';
    if (!window.confirm(`${headline}\n\n${detail}\n\n${tail}`)) return;
    setActing(true); setErr('');
    try {
      const { data } = await api.post(`/quality/cross-field/fix/${ruleId}`, { action });
      setToast(`${data.rows_dropped} row(s) dropped — ${data.rows_remaining} remaining`);
      setFailingFor(null);
      // Run the parent's refresh (e.g. Cleansing's loadAll) and the
      // dataset context refresh in parallel so the row count above
      // updates immediately — without this the page reads its cached
      // /quality/config response from before the rows were dropped.
      await Promise.all([
        load(),
        refresh(),
        onAfterFix ? onAfterFix() : Promise.resolve(),
      ]);
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Failed to apply fix');
    } finally {
      setActing(false);
    }
  };

  const exportCsv = async (ruleId) => {
    if (acting) return;
    setActing(true); setErr('');
    try {
      const resp = await api.get(`/quality/cross-field/export/${ruleId}`, {
        responseType: 'blob',
      });
      // Pull filename from Content-Disposition or fall back
      const cd = resp.headers['content-disposition'] || '';
      const m = cd.match(/filename="?([^";]+)"?/i);
      const fname = m ? m[1] : `failing_rule_${ruleId}.csv`;
      const url = window.URL.createObjectURL(new Blob([resp.data], { type: 'text/csv' }));
      const a = document.createElement('a');
      a.href = url; a.download = fname; a.click();
      window.URL.revokeObjectURL(url);
      setToast('CSV downloaded');
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Failed to export CSV');
    } finally {
      setActing(false);
    }
  };

  const total = rules.length;
  const totalIssues = rules.reduce((acc, r) => acc + (r.count || 0), 0);
  const evaluable = rules.filter((r) => r.family !== 'manual').length;

  return (
    <Paper variant="outlined" sx={{ mt: 3, p: 2 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }}>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 700 }}>
            Cross-field Rules
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {evaluated
              ? `${total} rules · ${evaluable} auto-evaluable · ${totalIssues} total issues`
              : 'Run the Rule Generator to populate cross-field rules.'}
          </Typography>
        </Box>
        <Button size="small" startIcon={<RefreshIcon />} onClick={load} disabled={loading}>
          Refresh
        </Button>
      </Stack>

      {loading && <LinearProgress sx={{ mb: 1 }} />}
      {err && <Alert severity="error" sx={{ mb: 1 }}>{err}</Alert>}

      {evaluated && total === 0 && (
        <Alert severity="info">
          No cross-field rules were generated. Run the Rule Generator first.
        </Alert>
      )}

      {total > 0 && (
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ fontWeight: 600, minWidth: 200 }}>Critical data elements</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Rule</TableCell>
                <TableCell sx={{ fontWeight: 600, width: 160 }}>Family</TableCell>
                <TableCell sx={{ fontWeight: 600, minWidth: 220 }}>Validation Expression</TableCell>
                <TableCell sx={{ fontWeight: 600, width: 90 }} align="right">Issues</TableCell>
                <TableCell sx={{ fontWeight: 600, width: 70 }} align="center">Rows</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rules.map((r) => {
                const palette = FAMILY_COLOR[r.family] || FAMILY_COLOR.manual;
                const isFailing = (r.count || 0) > 0;
                const isManual = r.family === 'manual';
                return (
                  <TableRow key={r.id} hover>
                    <TableCell sx={{ fontWeight: 600, fontSize: '0.82rem' }}>{r.columns}</TableCell>
                    <TableCell sx={{ fontSize: '0.82rem' }}>{r.rule}</TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        label={FAMILY_LABEL[r.family] || r.family}
                        sx={{
                          bgcolor: palette.bg,
                          color: palette.fg,
                          fontWeight: 600,
                          fontSize: '0.7rem',
                          height: 22,
                          borderRadius: 1,
                        }}
                      />
                    </TableCell>
                    <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.74rem', color: 'text.secondary' }}>
                      {r.expression || (isManual ? '—' : '')}
                    </TableCell>
                    <TableCell align="right" sx={{
                      fontVariantNumeric: 'tabular-nums',
                      fontWeight: 700,
                      color: isManual ? 'text.disabled' : isFailing ? 'error.main' : 'text.disabled',
                    }}>
                      {isManual ? '—' : r.count}
                    </TableCell>
                    <TableCell align="center">
                      <IconButton
                        size="small"
                        onClick={() => viewFailing(r)}
                        disabled={isManual || !isFailing}
                        title={isManual ? 'Cannot auto-evaluate'
                              : !isFailing ? 'No failing rows' : 'View failing rows'}
                      >
                        <VisibilityIcon fontSize="small" />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <Dialog open={!!failingFor} onClose={() => setFailingFor(null)} maxWidth="lg" fullWidth>
        <DialogTitle sx={{ pr: 6 }}>
          Failing Rows
          <IconButton sx={{ position: 'absolute', right: 8, top: 8 }}
            onClick={() => setFailingFor(null)}>
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent dividers>
          {failingFor && (
            <>
              <Typography variant="body2" sx={{ mb: 0.5 }}>{failingFor.rule}</Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontFamily: 'monospace' }}>
                {failingFor.expression}
              </Typography>
              <Stack direction="row" spacing={1} sx={{ mt: 1.5, mb: 1.5 }}>
                <Chip size="small" label={`${failingFor.count} failing rows`} color="error" />
                <Chip size="small" label={FAMILY_LABEL[failingFor.family] || failingFor.family} />
              </Stack>
              {failingFor.sample.length === 0 ? (
                <Alert severity="info">No sample rows available.</Alert>
              ) : (
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        {failingFor.columns.map((c) => (
                          <TableCell key={c} sx={{ fontWeight: 600, bgcolor: '#f1f5f9' }}>{c}</TableCell>
                        ))}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {failingFor.sample.map((row, i) => (
                        <TableRow key={i}>
                          {failingFor.columns.map((c) => (
                            <TableCell key={c} sx={{ fontFamily: 'monospace', fontSize: '0.78rem' }}>
                              {row[c] == null ? '' : String(row[c])}
                            </TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </>
          )}
        </DialogContent>
        <DialogActions sx={{ flexWrap: 'wrap', gap: 1, justifyContent: 'space-between', px: 3, pb: 2 }}>
          <Box>
            {failingFor && failingFor.count > 0 && (
              <Button
                onClick={() => exportCsv(failingFor.id)}
                disabled={acting}
                startIcon={<DownloadIcon />}
                variant="outlined"
              >
                Export CSV
              </Button>
            )}
          </Box>
          <Stack direction="row" spacing={1}>
            <Button onClick={() => setFailingFor(null)} disabled={acting}>Close</Button>
            {failingFor && failingFor.count > 0 && failingFor.family === 'composite_unique' && (
              <Button
                onClick={() => applyFix('deduplicate', failingFor.id, failingFor.family, failingFor.count)}
                disabled={acting}
                startIcon={<FilterAltOffOutlinedIcon />}
                variant="contained"
                color="warning"
              >
                Deduplicate (keep first)
              </Button>
            )}
            {failingFor && failingFor.count > 0
              && failingFor.family !== 'manual'
              && failingFor.family !== 'composite_unique' && (
              <Button
                onClick={() => applyFix('drop', failingFor.id, failingFor.family, failingFor.count)}
                disabled={acting}
                startIcon={<DeleteOutlineIcon />}
                variant="contained"
                color="error"
              >
                Drop {failingFor.count} row{failingFor.count === 1 ? '' : 's'}
              </Button>
            )}
          </Stack>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={!!toast}
        autoHideDuration={4000}
        onClose={() => setToast('')}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        message={toast}
      />
    </Paper>
  );
}
