import { useEffect, useMemo, useState } from 'react';
import {
  Box, Stack, Typography, Button, Chip, Alert, LinearProgress,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper,
  Tooltip,
} from '@mui/material';
import LibraryBooksOutlinedIcon from '@mui/icons-material/LibraryBooksOutlined';
import PlayArrowOutlinedIcon from '@mui/icons-material/PlayArrowOutlined';
import VisibilityOutlinedIcon from '@mui/icons-material/VisibilityOutlined';
import BoltOutlinedIcon from '@mui/icons-material/BoltOutlined';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import api from '../../api.js';
import StatCard from '../../components/StatCard.jsx';
import { useProject } from '../../context/ProjectContext.jsx';
import GoldenRecordDialog from './GoldenRecordDialog.jsx';
import ColumnMappingDialog from './ColumnMappingDialog.jsx';

const SEVERITY = {
  high:   { bg: '#FBEAEA', fg: '#D14343', label: 'High' },
  medium: { bg: '#FCF3E2', fg: '#7A4F09', label: 'Medium' },
  low:    { bg: '#E8F4ED', fg: '#14532D', label: 'Low' },
};

// Action class tells the operator how the rule should be treated downstream.
// auto_merge = safe to bulk-apply without per-group review.
// review_required = strong signal but a human should approve each group.
// flag_only = do NOT auto-merge — surfaces a fraud/audit signal.
const ACTION_CLASS = {
  auto_merge:       { bg: '#E8F4ED', fg: '#14532D', label: 'Auto-merge', icon: '⚡' },
  review_required:  { bg: '#E6F0FC', fg: '#1E3A8A', label: 'Review',     icon: '👁' },
  flag_only:        { bg: '#FBEAEA', fg: '#7F1D1D', label: 'Flag only',  icon: '⚠' },
};

export default function LibraryRulesTab() {
  const { active } = useProject();
  const stream = active?.stream?.id;
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [scanResult, setScanResult] = useState(null);  // { rule_id, dup_type, summaries, survivorship }
  const [reviewGroup, setReviewGroup] = useState(null); // { dup_type, group_id, rule_id }
  const [scanBusy, setScanBusy] = useState(false);
  const [mappingPrompt, setMappingPrompt] = useState(null);  // structured error from backend
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkStatus, setBulkStatus] = useState('');
  const [bulkSummary, setBulkSummary] = useState(null);

  useEffect(() => {
    setLoading(true);
    api
      .get('/duplicates/library', { params: stream ? { stream } : {} })
      .then(({ data }) => setRules(data.rules || []))
      .catch((e) => setError(e?.response?.data?.detail || 'Could not load library'))
      .finally(() => setLoading(false));
  }, [stream]);

  const scan = async (ruleId, columnMapping = null) => {
    setScanBusy(true);
    setError('');
    setScanResult(null);
    try {
      const body = { rule_id: ruleId };
      if (columnMapping) body.column_mapping = columnMapping;
      const { data } = await api.post('/duplicates/library/scan', body);
      setScanResult(data);
      setMappingPrompt(null);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      // Backend returns a structured 400 when columns need mapping.
      if (detail && typeof detail === 'object' && detail.code === 'missing_columns') {
        setMappingPrompt(detail);
      } else if (typeof detail === 'string') {
        setError(detail);
      } else if (detail?.message) {
        setError(detail.message);
      } else {
        setError(e?.message || 'Scan failed');
      }
    } finally {
      setScanBusy(false);
    }
  };

  const counts = useMemo(() => ({
    total: rules.length,
    high: rules.filter((r) => r.severity === 'high').length,
    fuzzy: rules.filter((r) => r.match_strategy === 'fuzzy').length,
    exact: rules.filter((r) => r.match_strategy === 'exact').length,
  }), [rules]);

  const autoMergeRules = useMemo(
    () => rules.filter((r) => r.action_class === 'auto_merge'),
    [rules],
  );

  // Run every auto_merge rule end-to-end: scan → apply each group with
  // the rule's bundled survivorship → re-scan (because indices shift on
  // each apply) → repeat until the scan returns zero groups for that
  // rule, then move to the next rule.
  const runAllAutoMerge = async () => {
    if (autoMergeRules.length === 0) return;
    const confirmed = window.confirm(
      `Auto-merge ${autoMergeRules.length} rule${autoMergeRules.length === 1 ? '' : 's'} ` +
      'without per-group review? Rules tagged Review or Flag only are skipped. ' +
      'You can reset the dataset from the Compare tab afterwards.',
    );
    if (!confirmed) return;

    setBulkBusy(true);
    setError('');
    setBulkSummary(null);
    setScanResult(null);

    const summary = { rulesRun: 0, rulesSkipped: 0, groupsMerged: 0, rowsDropped: 0 };
    const MAX_GROUPS_PER_RULE = 100;  // safety cap

    for (const rule of autoMergeRules) {
      setBulkStatus(`Running ${rule.label}…`);
      let appliedForThisRule = 0;
      for (let i = 0; i < MAX_GROUPS_PER_RULE; i++) {
        let scanRes;
        try {
          const r = await api.post('/duplicates/library/scan', { rule_id: rule.id });
          scanRes = r.data;
        } catch (e) {
          // Column mapping required — can't auto-merge without user input.
          const detail = e?.response?.data?.detail;
          if (detail?.code === 'missing_columns') {
            summary.rulesSkipped += 1;
          }
          break;
        }
        if (!scanRes?.summaries?.length) break;
        const first = scanRes.summaries[0];
        try {
          const apply = await api.post(
            `/duplicates/${scanRes.dup_type}/group/${first.group_id}/apply-golden`,
            { rule_id: rule.id },
          );
          appliedForThisRule += 1;
          summary.groupsMerged += 1;
          summary.rowsDropped += apply.data.rows_dropped || 0;
        } catch (e) {
          break;
        }
      }
      if (appliedForThisRule > 0) summary.rulesRun += 1;
    }

    setBulkBusy(false);
    setBulkStatus('');
    setBulkSummary(summary);
  };

  return (
    <Box>
      <Stack
        direction={{ xs: 'column', md: 'row' }}
        justifyContent="space-between"
        alignItems={{ xs: 'flex-start', md: 'center' }}
        spacing={1.5}
        sx={{ mb: 1 }}
      >
        <Stack direction="row" alignItems="center" spacing={1}>
          <LibraryBooksOutlinedIcon sx={{ color: '#6A28A8' }} />
          <Typography
            sx={{
              fontFamily: "'Montserrat', sans-serif",
              fontSize: 18,
              fontWeight: 700,
              color: '#1A1A1A',
            }}
          >
            Duplicate-rule library
          </Typography>
          {stream && (
            <Chip
              size="small"
              label={`stream: ${stream}`}
              sx={{ height: 20, fontSize: '0.7rem', bgcolor: '#F4ECF9', color: '#6A28A8' }}
            />
          )}
        </Stack>
        {autoMergeRules.length > 0 && (
          <Tooltip
            title={
              `Runs the ${autoMergeRules.length} auto-merge rule${autoMergeRules.length === 1 ? '' : 's'} sequentially — ` +
              'each rule scans, then merges every group it finds using the rule\'s bundled survivorship. ' +
              'Review and Flag-only rules are skipped.'
            }
          >
            <span>
              <Button
                variant="contained"
                startIcon={<BoltOutlinedIcon />}
                onClick={runAllAutoMerge}
                disabled={bulkBusy || scanBusy}
                sx={{ py: 1, px: 2, fontWeight: 700 }}
              >
                Run all auto-merge ({autoMergeRules.length})
              </Button>
            </span>
          </Tooltip>
        )}
      </Stack>
      <Typography sx={{ fontSize: 13, color: '#555555', mb: 2 }}>
        Pre-built duplicate-detection rules with bundled survivorship
        strategies. Pick one and run it against the current dataset, or
        bulk-apply every safe rule with the action button above.
      </Typography>

      {bulkBusy && (
        <Box sx={{ mb: 2 }}>
          <LinearProgress sx={{ mb: 1 }} />
          <Typography sx={{ fontSize: 12.5, color: '#555555' }}>{bulkStatus}</Typography>
        </Box>
      )}
      {bulkSummary && !bulkBusy && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setBulkSummary(null)}>
          Bulk auto-merge complete. Ran <b>{bulkSummary.rulesRun}</b> rule
          {bulkSummary.rulesRun === 1 ? '' : 's'}, merged <b>{bulkSummary.groupsMerged}</b> group
          {bulkSummary.groupsMerged === 1 ? '' : 's'}, dropped <b>{bulkSummary.rowsDropped}</b> row
          {bulkSummary.rowsDropped === 1 ? '' : 's'}.
          {bulkSummary.rulesSkipped > 0 && (
            <> Skipped <b>{bulkSummary.rulesSkipped}</b> rule{bulkSummary.rulesSkipped === 1 ? '' : 's'} that needed critical data element mapping.</>
          )}
        </Alert>
      )}

      {loading && <LinearProgress sx={{ mb: 2 }} />}
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {rules.length === 0 && !loading && (
        <Alert severity="info">
          No library rules for {stream ? `the ${stream} stream` : 'this project'}.
          The canonical rules are seeded in
          {' '}<code>backend/library/dedup_rules.json</code>.
        </Alert>
      )}

      {rules.length > 0 && (
        <TableContainer component={Paper} variant="outlined" sx={{ mb: 3 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ fontWeight: 700 }}>Rule</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Match strategy</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Critical data elements</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Survivorship</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Action</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Severity</TableCell>
                <TableCell sx={{ fontWeight: 700, width: 110 }} />
              </TableRow>
            </TableHead>
            <TableBody>
              {rules.map((r) => {
                const sev = SEVERITY[r.severity] || SEVERITY.medium;
                const action = ACTION_CLASS[r.action_class] || null;
                const cols = (r.match_columns || [])
                  .map((m) => `${m.column}${m.threshold ? ` ≥${Math.round(m.threshold * 100)}%` : ''}`)
                  .join(' + ');
                return (
                  <TableRow key={r.id} hover>
                    <TableCell>
                      <Stack direction="row" alignItems="center" spacing={0.5}>
                        <Typography sx={{ fontSize: 13.5, fontWeight: 600 }}>{r.label}</Typography>
                        {r.notes && (
                          <Tooltip
                            title={
                              <Box sx={{ p: 0.5 }}>
                                <Typography sx={{ fontSize: 12, fontWeight: 700, mb: 0.5 }}>
                                  Why this rule?
                                </Typography>
                                <Typography sx={{ fontSize: 12, lineHeight: 1.4 }}>
                                  {r.notes}
                                </Typography>
                              </Box>
                            }
                            arrow
                            placement="right"
                          >
                            <InfoOutlinedIcon
                              sx={{ fontSize: 14, color: '#8A8A8A', cursor: 'help' }}
                            />
                          </Tooltip>
                        )}
                      </Stack>
                      <Typography sx={{ fontSize: 12, color: '#8A8A8A' }}>{r.description}</Typography>
                    </TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        label={r.match_strategy}
                        variant="outlined"
                        sx={{ height: 22, fontSize: '0.72rem' }}
                      />
                    </TableCell>
                    <TableCell sx={{ fontFamily: 'ui-monospace, Menlo, monospace', fontSize: '0.78rem' }}>
                      {cols}
                    </TableCell>
                    <TableCell>
                      <Tooltip title={JSON.stringify(r.survivorship || {})}>
                        <Chip
                          size="small"
                          label={r.survivorship?.strategy || 'most_complete'}
                          sx={{ height: 22, fontSize: '0.72rem', bgcolor: '#F4ECF9', color: '#6A28A8' }}
                        />
                      </Tooltip>
                    </TableCell>
                    <TableCell>
                      {action ? (
                        <Chip
                          size="small"
                          label={`${action.icon} ${action.label}`}
                          sx={{
                            height: 22,
                            fontSize: '0.72rem',
                            fontWeight: 700,
                            bgcolor: action.bg,
                            color: action.fg,
                          }}
                        />
                      ) : (
                        <Chip size="small" label="—" variant="outlined" sx={{ height: 22 }} />
                      )}
                    </TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        label={sev.label}
                        sx={{ height: 22, fontSize: '0.72rem', fontWeight: 700, bgcolor: sev.bg, color: sev.fg }}
                      />
                    </TableCell>
                    <TableCell>
                      <Button
                        size="small"
                        variant="contained"
                        startIcon={<PlayArrowOutlinedIcon />}
                        onClick={() => scan(r.id)}
                        disabled={scanBusy || bulkBusy}
                      >
                        Run
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {scanBusy && <LinearProgress sx={{ mb: 2 }} />}

      {scanResult && (
        <>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
            <Typography
              sx={{
                fontFamily: "'Montserrat', sans-serif",
                fontSize: 17,
                fontWeight: 700,
                color: '#1A1A1A',
              }}
            >
              Scan results
            </Typography>
            <Chip
              size="small"
              label={scanResult.label || scanResult.rule_id}
              sx={{ height: 20, fontSize: '0.7rem', bgcolor: '#F4ECF9', color: '#6A28A8' }}
            />
          </Stack>

          <Stack direction="row" spacing={1.5} sx={{ mb: 2 }}>
            <StatCard accent label="Groups" value={scanResult.total_groups} />
            <StatCard label="Rows affected" value={scanResult.total_rows} />
            <StatCard
              label="Survivorship"
              value={scanResult.survivorship?.strategy || 'most_complete'}
            />
          </Stack>

          <TableContainer component={Paper} variant="outlined">
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 700 }}>Group</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Members</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Match key</TableCell>
                  <TableCell sx={{ fontWeight: 700, width: 180 }} />
                </TableRow>
              </TableHead>
              <TableBody>
                {(scanResult.summaries || []).map((g) => {
                  const memberCount = g.rows ?? g.row_count ?? g.indices?.length ?? 0;
                  const matchKey = g.representative || g.match_key || g.match_value || '';
                  const keyCols = Array.isArray(g.key_columns) ? g.key_columns.join(' + ') : '';
                  return (
                  <TableRow key={g.group_id} hover>
                    <TableCell sx={{ fontFamily: 'ui-monospace, Menlo, monospace' }}>
                      #{g.group_id}
                    </TableCell>
                    <TableCell>{memberCount}</TableCell>
                    <TableCell sx={{ fontSize: '0.78rem', color: '#555555' }}>
                      <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                        {keyCols && (
                          <Typography sx={{ fontSize: '0.7rem', color: '#8A8A8A', fontFamily: 'ui-monospace, Menlo, monospace' }}>
                            {keyCols}
                          </Typography>
                        )}
                        <Typography
                          sx={{ fontSize: '0.78rem', color: '#1A1A1A', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 360 }}
                          title={matchKey}
                        >
                          {matchKey || <em style={{ color: '#8A8A8A' }}>—</em>}
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Button
                        size="small"
                        variant="outlined"
                        startIcon={<VisibilityOutlinedIcon />}
                        onClick={() =>
                          setReviewGroup({
                            dup_type: scanResult.dup_type,
                            group_id: g.group_id,
                            rule_id: scanResult.rule_id,
                          })
                        }
                      >
                        Review golden
                      </Button>
                    </TableCell>
                  </TableRow>
                  );
                })}
                {(!scanResult.summaries || scanResult.summaries.length === 0) && (
                  <TableRow>
                    <TableCell colSpan={4} align="center" sx={{ py: 3, color: '#8A8A8A' }}>
                      No duplicate groups matched this rule.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </>
      )}

      <GoldenRecordDialog
        open={!!reviewGroup}
        onClose={() => setReviewGroup(null)}
        dup_type={reviewGroup?.dup_type}
        group_id={reviewGroup?.group_id}
        rule_id={reviewGroup?.rule_id}
        onApplied={() => {
          setReviewGroup(null);
          // Re-run the scan so the resolved group disappears from the list.
          if (scanResult?.rule_id) scan(scanResult.rule_id);
        }}
      />

      <ColumnMappingDialog
        open={!!mappingPrompt}
        onClose={() => setMappingPrompt(null)}
        onConfirm={(mapping) => {
          const ruleId = mappingPrompt?.rule_id;
          setMappingPrompt(null);
          if (ruleId) scan(ruleId, mapping);
        }}
        ruleLabel={mappingPrompt?.rule_label}
        ruleColumns={mappingPrompt?.rule_columns || []}
        missingColumns={mappingPrompt?.missing_columns || []}
        availableColumns={mappingPrompt?.available_columns || []}
        suggestedMapping={mappingPrompt?.suggested_mapping || {}}
      />
    </Box>
  );
}
