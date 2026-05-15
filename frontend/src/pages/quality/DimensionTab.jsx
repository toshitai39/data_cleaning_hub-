import { useMemo, useState } from 'react';
import {
  Box, Stack, Typography, Button, Chip, Alert, Paper, Divider, ToggleButtonGroup, ToggleButton,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Tooltip, IconButton, LinearProgress,
} from '@mui/material';
import VisibilityOutlinedIcon from '@mui/icons-material/VisibilityOutlined';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import PlayArrowOutlinedIcon from '@mui/icons-material/PlayArrowOutlined';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import PersonOutlineIcon from '@mui/icons-material/PersonOutline';
import ReportProblemOutlinedIcon from '@mui/icons-material/ReportProblemOutlined';
import api from '../../api.js';

// Status palette — calm, low-saturation neutrals so the eye reads the
// number first, not the color. Only Actionable + Applied carry a hint
// of red/green; everything else is grayscale to de-emphasize noise.
const STATUS_STYLE = {
  actionable:         { bg: '#fef2f2', fg: '#b91c1c', label: 'Actionable' },
  passed:             { bg: '#f0fdf4', fg: '#15803d', label: 'Passed' },
  applied:            { bg: '#f0fdf4', fg: '#15803d', label: 'Applied' },
  unmapped:           { bg: '#f8fafc', fg: '#64748b', label: 'Unmapped' },
  blocked_empty:      { bg: '#f8fafc', fg: '#64748b', label: 'Blocked · empty' },
  blocked_incomplete: { bg: '#f8fafc', fg: '#64748b', label: 'Blocked · low fill' },
  multi_cde:          { bg: '#f5f5f4', fg: '#57534e', label: 'Multi-CDE' },
  invalid:            { bg: '#f5f5f4', fg: '#57534e', label: 'Invalid' },
};

function StatusChip({ status }) {
  const cfg = STATUS_STYLE[status] || { bg: '#f3f4f6', fg: '#6b7280', label: status };
  return (
    <Chip
      size="small"
      label={cfg.label}
      sx={{ height: 20, fontSize: '0.68rem', fontWeight: 700, bgcolor: cfg.bg, color: cfg.fg }}
    />
  );
}

function SourceChip({ source }) {
  const isAi = source === 'ai';
  const Icon = isAi ? AutoAwesomeIcon : PersonOutlineIcon;
  return (
    <Chip
      size="small"
      icon={<Icon sx={{ fontSize: 13 }} />}
      label={isAi ? 'AI' : 'Custom'}
      sx={{
        height: 20, fontSize: '0.68rem', fontWeight: 600,
        bgcolor: isAi ? '#faf5ff' : '#fff7ed',
        color: isAi ? '#581c87' : '#9a3412',
        '& .MuiChip-icon': { color: isAi ? '#581c87' : '#9a3412' },
      }}
    />
  );
}

// Lifecycle-driven rule review panel. Every generated rule shows up
// here in exactly one status — no silent drops, no hidden state.
export default function DimensionTab({ dimension, data, onAfterChange }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const [filter, setFilter] = useState('actionable');
  const [previewKey, setPreviewKey] = useState(null);
  const [previewData, setPreviewData] = useState(null);
  const [failingRowsFor, setFailingRowsFor] = useState(null);
  const [failingRowsData, setFailingRowsData] = useState(null);

  // Derive counts/rules safely — data may be null until first fetch.
  const counts = data?.counts || {};
  const rules = data?.rules || [];

  const FILTER_OPTIONS = [
    { value: 'all',                 label: 'All',         count: rules.length },
    { value: 'actionable',          label: 'Actionable',  count: counts.actionable || 0 },
    { value: 'passed',              label: 'Passed',      count: counts.passed || 0 },
    { value: 'applied',             label: 'Applied',     count: counts.applied || 0 },
    { value: 'unmapped',            label: 'Unmapped',    count: counts.unmapped || 0 },
    { value: 'blocked_empty',       label: 'Empty col',   count: counts.blocked_empty || 0 },
    { value: 'blocked_incomplete',  label: 'Incomplete',  count: counts.blocked_incomplete || 0 },
    { value: 'invalid',             label: 'Invalid',     count: counts.invalid || 0 },
  ].filter((f) => f.value === 'all' || f.value === 'actionable' || f.count > 0);

  // ALL hooks must be declared before any conditional return.
  const visibleRules = useMemo(() => {
    if (filter === 'all') return rules;
    return rules.filter((r) => r.status === filter);
  }, [rules, filter]);

  // Early returns come AFTER all hooks.
  if (!data) {
    return <Alert severity="info">No data for this dimension yet.</Alert>;
  }

  // Imported AI rules (status=actionable, has rule_idx in dq_config) can
  // be previewed/applied directly. Unimported AI rules surface as
  // actionable too but need to be imported first.
  const importMissingAi = async () => {
    setBusy(true); setErr(''); setMsg('');
    try {
      const { data: r } = await api.post(`/quality/import-ai/${encodeURIComponent(dimension)}`);
      setMsg(r.imported > 0 ? `Imported ${r.imported} AI rules into pending` : 'Already imported');
      onAfterChange?.();
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Import failed');
    } finally { setBusy(false); }
  };

  const previewRule = async (rule) => {
    if (rule.rule_idx == null) {
      // Try importing this dimension first so the rule has a rule_idx.
      await importMissingAi();
      return;
    }
    setBusy(true); setErr('');
    setPreviewKey(`${rule.column}-${rule.rule_idx}`);
    setPreviewData(null);
    try {
      const { data: r } = await api.post(
        `/quality/preview-rule/${encodeURIComponent(rule.column)}/${rule.rule_idx}`,
      );
      setPreviewData({ column: rule.column, ...r, name: rule.name });
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Preview failed');
      setPreviewKey(null);
    } finally { setBusy(false); }
  };

  const applyRule = async (rule) => {
    if (rule.rule_idx == null) {
      await importMissingAi();
      return;
    }
    setBusy(true); setErr(''); setMsg('');
    try {
      const { data: r } = await api.post(
        `/quality/apply-rule/${encodeURIComponent(rule.column)}/${rule.rule_idx}`,
      );
      setMsg(`Applied "${rule.name}" · ${r.rejected} row${r.rejected === 1 ? '' : 's'} rejected`);
      setPreviewKey(null);
      setPreviewData(null);
      onAfterChange?.();
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Apply failed');
    } finally { setBusy(false); }
  };

  const showFailingRows = async (rule) => {
    setBusy(true); setErr('');
    setFailingRowsFor({ column: rule.column, rule_text: rule.rule_text || rule.name });
    setFailingRowsData(null);
    try {
      const { data: r } = await api.post('/quality/failing-rows', {
        column: rule.column,
        rule_text: rule.rule_text || rule.name || '',
        regex_pattern: rule.pattern || '',
        dimension,
        limit: 20,
      });
      setFailingRowsData(r);
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Could not fetch failing rows');
      setFailingRowsFor(null);
    } finally { setBusy(false); }
  };

  const dropRule = async (rule) => {
    setBusy(true); setErr(''); setMsg('');
    try {
      await api.post('/quality/drop-rule', {
        rule_id: rule.rule_id >= 0 ? rule.rule_id : null,
        column: rule.rule_idx != null ? rule.column : null,
        rule_idx: rule.rule_idx,
      });
      setMsg('Rule dropped');
      onAfterChange?.();
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Drop failed');
    } finally { setBusy(false); }
  };

  const applyDimension = async () => {
    setBusy(true); setErr(''); setMsg('');
    try {
      // Make sure every actionable rule is imported into dq_config first.
      await api.post(`/quality/import-ai/${encodeURIComponent(dimension)}`);
      const { data: r } = await api.post(`/quality/apply-dimension/${encodeURIComponent(dimension)}`);
      setMsg(`Applied ${r.applied} rules across ${r.columns.length} CDEs · ${r.rejected} rows rejected`);
      onAfterChange?.();
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Apply failed');
    } finally { setBusy(false); }
  };

  // Uniqueness — defer to Find Duplicates
  if (dimension === 'Uniqueness' && counts.actionable === 0 && rules.length > 0) {
    return (
      <Alert
        severity="info"
        action={
          <Button color="inherit" size="small" href="#/find-duplicates">
            Open Find Duplicates
          </Button>
        }
      >
        Uniqueness rules ({rules.length}) are resolved on the <b>Find Duplicates</b> tab.
        Use exact / fuzzy / custom dedup scans there.
      </Alert>
    );
  }

  return (
    <Box>
      {busy && <LinearProgress sx={{ mb: 1.5 }} />}
      {err && <Alert severity="error" sx={{ mb: 1.5 }} onClose={() => setErr('')}>{err}</Alert>}
      {msg && <Alert severity="success" sx={{ mb: 1.5 }} onClose={() => setMsg('')}>{msg}</Alert>}

      {/* Lifecycle summary line */}
      <Stack direction="row" alignItems="center" spacing={1.5} flexWrap="wrap" sx={{ mb: 1.5 }}>
        <Typography sx={{ fontSize: 14, color: '#1A1A1A', fontWeight: 600 }}>
          {data.generated_count || 0} {dimension} rule{(data.generated_count || 0) === 1 ? '' : 's'}
        </Typography>
        <Typography sx={{ fontSize: 13, color: '#555555' }}>
          · <b>{counts.actionable || 0}</b> actionable
          {(counts.passed || 0) > 0 && <> · <b>{counts.passed}</b> passed</>}
          {(counts.applied || 0) > 0 && <> · <b>{counts.applied}</b> applied</>}
          {(counts.unmapped || 0) > 0 && <> · <b>{counts.unmapped}</b> unmapped</>}
          {(counts.blocked_empty || 0) > 0 && <> · <b>{counts.blocked_empty}</b> blocked (empty)</>}
          {(counts.blocked_incomplete || 0) > 0 && <> · <b>{counts.blocked_incomplete}</b> blocked (low fill)</>}
          {(counts.invalid || 0) > 0 && <> · <b>{counts.invalid}</b> invalid</>}
        </Typography>
        {data.failing_rows_total > 0 && (
          <Chip
            size="small"
            label={`${data.failing_rows_total.toLocaleString()} failing rows`}
            sx={{ height: 22, fontSize: '0.72rem', fontWeight: 700, bgcolor: '#fef2f2', color: '#b91c1c' }}
          />
        )}
      </Stack>

      {/* Filter chips */}
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }} flexWrap="wrap" gap={1}>
        <ToggleButtonGroup
          size="small"
          value={filter}
          exclusive
          onChange={(_, v) => v && setFilter(v)}
          sx={{
            flexWrap: 'wrap',
            '& .MuiToggleButton-root': {
              textTransform: 'none',
              fontSize: '0.75rem',
              px: 1.25,
              py: 0.3,
              fontWeight: 600,
              border: '1px solid #E7E6E6',
            },
          }}
        >
          {FILTER_OPTIONS.map((f) => (
            <ToggleButton key={f.value} value={f.value}>
              {f.label} <Chip size="small" label={f.count} sx={{ ml: 0.75, height: 16, fontSize: '0.62rem', fontWeight: 700 }} />
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
        {(counts.actionable || 0) > 0 && (
          <Button
            variant="contained"
            size="small"
            startIcon={<CheckCircleOutlineIcon />}
            onClick={applyDimension}
            disabled={busy}
            sx={{ textTransform: 'none', fontWeight: 700 }}
          >
            Apply all {counts.actionable} in {dimension}
          </Button>
        )}
      </Stack>

      {visibleRules.length === 0 ? (
        <Alert severity="info">
          No rules match this filter.{' '}
          {filter !== 'all' && filter !== 'actionable' && rules.length > 0 && (
            <Button size="small" onClick={() => setFilter('all')}>Show all</Button>
          )}
        </Alert>
      ) : (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ fontWeight: 700, width: 160 }}>Critical data element</TableCell>
                <TableCell sx={{ fontWeight: 700, width: 80 }}>Source</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Rule</TableCell>
                <TableCell sx={{ fontWeight: 700, width: 130 }}>Status</TableCell>
                <TableCell sx={{ fontWeight: 700, width: 90 }}>Failing</TableCell>
                <TableCell sx={{ fontWeight: 700, width: 200 }} align="right">Action</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {visibleRules.map((r, i) => (
                <TableRow key={`${r.rule_id}-${r.column}-${i}`} hover sx={{ verticalAlign: 'top' }}>
                  <TableCell sx={{ fontFamily: 'ui-monospace, Menlo, monospace', fontSize: '0.78rem', fontWeight: 600 }}>
                    {r.column}
                    {r.is_multi_cde && (
                      <Typography sx={{ fontSize: '0.65rem', color: '#8A8A8A', mt: 0.25 }}>
                        + {(r.atomic_columns || []).filter((c) => c !== r.column).join(', ')}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell><SourceChip source={r.source} /></TableCell>
                  <TableCell>
                    <Typography sx={{ fontSize: '0.82rem', color: '#1A1A1A', fontWeight: 500 }}>
                      {r.rule_text || r.name || `${r.mode} rule`}
                    </Typography>
                    {r.pattern && (
                      <Typography sx={{ fontSize: '0.7rem', color: '#8A8A8A', fontFamily: 'ui-monospace, Menlo, monospace', mt: 0.25 }}>
                        {r.mode}: {r.pattern}
                      </Typography>
                    )}
                    {r.reason && (
                      <Typography sx={{ fontSize: '0.7rem', color: '#9a3412', mt: 0.5, fontStyle: 'italic' }}>
                        {r.reason}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell><StatusChip status={r.status} /></TableCell>
                  <TableCell>
                    {r.status === 'actionable' ? (
                      <Chip
                        size="small"
                        label={`${(r.failure_count || 0).toLocaleString()}`}
                        sx={{
                          height: 22, fontSize: '0.72rem', fontWeight: 700,
                          bgcolor: '#fef2f2', color: '#b91c1c',
                        }}
                      />
                    ) : r.status === 'passed' ? (
                      <Chip size="small" label="0" sx={{ height: 22, fontSize: '0.72rem', bgcolor: '#f0fdf4', color: '#15803d' }} />
                    ) : (
                      <Typography sx={{ fontSize: '0.72rem', color: '#9CA3AF' }}>—</Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={0.5} alignItems="center" justifyContent="flex-end">
                      {r.status === 'actionable' && (
                        <>
                          <Tooltip title="Preview sample rows">
                            <span>
                              <IconButton size="small" onClick={() => previewRule(r)} disabled={busy}>
                                <VisibilityOutlinedIcon sx={{ fontSize: 16 }} />
                              </IconButton>
                            </span>
                          </Tooltip>
                          <Tooltip title="View failing rows">
                            <span>
                              <IconButton size="small" onClick={() => showFailingRows(r)} disabled={busy}>
                                <ReportProblemOutlinedIcon sx={{ fontSize: 16 }} />
                              </IconButton>
                            </span>
                          </Tooltip>
                          <Tooltip title="Apply this rule">
                            <span>
                              <IconButton size="small" color="primary" onClick={() => applyRule(r)} disabled={busy}>
                                <PlayArrowOutlinedIcon sx={{ fontSize: 16 }} />
                              </IconButton>
                            </span>
                          </Tooltip>
                          <Tooltip title="Drop this rule">
                            <span>
                              <IconButton size="small" onClick={() => dropRule(r)} disabled={busy}>
                                <DeleteOutlineIcon sx={{ fontSize: 16 }} />
                              </IconButton>
                            </span>
                          </Tooltip>
                        </>
                      )}
                      {r.status === 'unmapped' && (
                        <Tooltip title="Drop this rule (no mechanical check available)">
                          <span>
                            <IconButton size="small" onClick={() => dropRule(r)} disabled={busy}>
                              <DeleteOutlineIcon sx={{ fontSize: 16 }} />
                            </IconButton>
                          </span>
                        </Tooltip>
                      )}
                      {(r.status === 'blocked_empty' || r.status === 'blocked_incomplete') && (
                        <Tooltip title="Drop this rule (column needs Completeness work first)">
                          <span>
                            <IconButton size="small" onClick={() => dropRule(r)} disabled={busy}>
                              <DeleteOutlineIcon sx={{ fontSize: 16 }} />
                            </IconButton>
                          </span>
                        </Tooltip>
                      )}
                      {r.status === 'invalid' && (
                        <Tooltip title="Drop this rule (column missing)">
                          <span>
                            <IconButton size="small" onClick={() => dropRule(r)} disabled={busy}>
                              <DeleteOutlineIcon sx={{ fontSize: 16 }} />
                            </IconButton>
                          </span>
                        </Tooltip>
                      )}
                    </Stack>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {/* Single-rule preview panel */}
      {previewKey && previewData && (
        <Paper variant="outlined" sx={{ mt: 2, p: 2 }}>
          <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 1.5 }}>
            <Typography sx={{ fontSize: 14, fontWeight: 700, flex: 1 }}>
              Preview: {previewData.column}
              {previewData.name && (
                <Typography component="span" sx={{ fontSize: 12, color: '#8A8A8A', ml: 1, fontWeight: 500 }}>
                  · {previewData.name}
                </Typography>
              )}
            </Typography>
            {!previewData.manual && !previewData.column_empty && (
              <Button
                variant="contained"
                size="small"
                startIcon={<PlayArrowOutlinedIcon />}
                onClick={() => {
                  const [col, idx] = previewKey.split('-');
                  applyRule({ column: col, rule_idx: parseInt(idx, 10), name: previewData.name });
                }}
                disabled={busy}
                sx={{ textTransform: 'none', fontWeight: 700 }}
              >
                Confirm & apply
              </Button>
            )}
            <Button size="small" onClick={() => { setPreviewKey(null); setPreviewData(null); }}>
              Close
            </Button>
          </Stack>
          <Divider sx={{ mb: 1.5 }} />
          {previewData.column_empty ? (
            <Alert severity="warning">{previewData.message}</Alert>
          ) : previewData.manual ? (
            <Alert severity="warning">{previewData.message || 'Manual review only.'}</Alert>
          ) : (previewData.rows || []).length === 0 ? (
            <Alert severity="success" sx={{ '& .MuiAlert-message': { width: '100%' } }}>
              <Typography sx={{ fontWeight: 700, fontSize: 14, mb: 0.5 }}>
                No problematic rows for this rule.
              </Typography>
              <Typography sx={{ fontSize: 13 }}>
                All {(previewData.total_rows || 0).toLocaleString()} row{previewData.total_rows === 1 ? '' : 's'} in
                {' '}<b>{previewData.column}</b> already pass <i>{previewData.rule_name || 'this rule'}</i> —
                applying it would reject 0 rows. Nothing to clean.
              </Typography>
            </Alert>
          ) : (() => {
            // Build the column list from the first row's keys. The
            // target column (the one the rule fires on) is rendered with
            // a soft red wash so the steward's eye lands on it first.
            // We append a final "After" column showing the rule's effect.
            const targetCol = previewData.column;
            const isTransform = previewData.is_transform;
            const totalFailing = previewData.total_failing || 0;
            const firstRow = previewData.rows[0] || {};
            const dataCols = Object.keys(firstRow).filter(
              (k) => k !== '_before' && k !== '_after' && k !== '_status',
            );
            // Move target column first so it's never hidden by scrolling.
            const orderedCols = [
              targetCol,
              ...dataCols.filter((c) => c !== targetCol),
            ];
            return (
              <>
                {!isTransform && totalFailing > 0 && (
                  <Alert severity="warning" sx={{ mb: 1.5 }}>
                    <b>{totalFailing.toLocaleString()}</b> row{totalFailing === 1 ? '' : 's'} would be rejected
                    {previewData.rows.length < totalFailing && ` · showing first ${previewData.rows.length}`}.
                  </Alert>
                )}
                {isTransform && (
                  <Alert severity="info" sx={{ mb: 1.5 }}>
                    This rule transforms values rather than rejecting rows — preview of the first {previewData.rows.length} row{previewData.rows.length === 1 ? '' : 's'}.
                  </Alert>
                )}
                <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 420 }}>
                  <Table size="small" stickyHeader>
                    <TableHead>
                      <TableRow>
                        {orderedCols.map((c, colIdx) => {
                          const isTarget = c === targetCol;
                          return (
                            <TableCell
                              key={c}
                              sx={{
                                fontWeight: 700,
                                fontSize: '0.7rem',
                                bgcolor: isTarget ? '#fef2f2' : '#fafafa',
                                color: isTarget ? '#b91c1c' : '#444',
                                // Sticky-left for the target column so the
                                // steward never loses it while scrolling
                                // a wide dataset's other columns.
                                position: isTarget ? 'sticky' : 'static',
                                left: isTarget ? 0 : 'auto',
                                zIndex: isTarget ? 3 : 1,
                                borderRight: isTarget ? '2px solid #fca5a5' : undefined,
                                minWidth: isTarget ? 160 : undefined,
                              }}
                            >
                              {c}{isTarget && ' ← rule'}
                            </TableCell>
                          );
                        })}
                        <TableCell sx={{ fontWeight: 700, fontSize: '0.7rem', width: 140, bgcolor: '#fafafa' }}>
                          After
                        </TableCell>
                        <TableCell sx={{ fontWeight: 700, fontSize: '0.7rem', width: 90, bgcolor: '#fafafa' }}>
                          Status
                        </TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {previewData.rows.map((row, i) => (
                        <TableRow key={i} hover>
                          {orderedCols.map((c) => {
                            const isTarget = c === targetCol;
                            return (
                              <TableCell
                                key={c}
                                sx={{
                                  fontFamily: 'ui-monospace, Menlo, monospace',
                                  fontSize: '0.72rem',
                                  bgcolor: isTarget ? '#fef2f2' : '#fff',
                                  color: isTarget ? '#1A1A1A' : '#555',
                                  fontWeight: isTarget ? 600 : 400,
                                  whiteSpace: 'nowrap',
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  maxWidth: 180,
                                  position: isTarget ? 'sticky' : 'static',
                                  left: isTarget ? 0 : 'auto',
                                  zIndex: isTarget ? 2 : 0,
                                  borderRight: isTarget ? '2px solid #fca5a5' : undefined,
                                  minWidth: isTarget ? 160 : undefined,
                                }}
                              >
                                {String(row[c] ?? '') || (isTarget ? <span style={{ color: '#b91c1c', fontStyle: 'italic' }}>(blank)</span> : '')}
                              </TableCell>
                            );
                          })}
                          <TableCell sx={{ fontFamily: 'ui-monospace, Menlo, monospace', fontSize: '0.72rem' }}>
                            {row._after}
                          </TableCell>
                          <TableCell>
                            <Chip
                              size="small"
                              label={row._status}
                              sx={{
                                height: 20, fontSize: '0.66rem',
                                bgcolor: row._status === 'Rejected' ? '#fef2f2' :
                                         row._status === 'Transform' ? '#eff6ff' : '#f0fdf4',
                                color: row._status === 'Rejected' ? '#b91c1c' :
                                       row._status === 'Transform' ? '#1e40af' : '#15803d',
                              }}
                            />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </>
            );
          })()}
        </Paper>
      )}

      {/* Failing rows inspector */}
      {failingRowsFor && (
        <Paper variant="outlined" sx={{ mt: 2, p: 2 }}>
          <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 1.5 }}>
            <Typography sx={{ fontSize: 14, fontWeight: 700, flex: 1 }}>
              Failing rows: {failingRowsFor.column}
              <Typography component="span" sx={{ fontSize: 12, color: '#8A8A8A', ml: 1, fontWeight: 500 }}>
                · {failingRowsFor.rule_text}
              </Typography>
            </Typography>
            <Button size="small" onClick={() => { setFailingRowsFor(null); setFailingRowsData(null); }}>Close</Button>
          </Stack>
          <Divider sx={{ mb: 1.5 }} />
          {!failingRowsData ? (
            <LinearProgress />
          ) : failingRowsData.manual ? (
            <Alert severity="warning">{failingRowsData.message}</Alert>
          ) : failingRowsData.total === 0 ? (
            <Alert severity="success">{failingRowsData.message || 'No failing rows.'}</Alert>
          ) : (
            <>
              <Alert severity="warning" sx={{ mb: 1.5 }}>
                <b>{failingRowsData.total.toLocaleString()}</b> rows violate this rule
                {failingRowsData.rows.length < failingRowsData.total && ` · showing first ${failingRowsData.rows.length}`}.
              </Alert>
              <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 360 }}>
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      {Object.keys(failingRowsData.rows[0] || {}).map((c) => (
                        <TableCell key={c} sx={{ fontWeight: 700, fontSize: '0.72rem' }}>{c}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {failingRowsData.rows.map((r, i) => (
                      <TableRow key={i}>
                        {Object.entries(r).map(([k, v]) => (
                          <TableCell
                            key={k}
                            sx={{
                              fontFamily: 'ui-monospace, Menlo, monospace',
                              fontSize: '0.72rem',
                              bgcolor: k === failingRowsFor.column ? '#fef2f2' : 'transparent',
                            }}
                          >
                            {String(v ?? '')}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </>
          )}
        </Paper>
      )}
    </Box>
  );
}
