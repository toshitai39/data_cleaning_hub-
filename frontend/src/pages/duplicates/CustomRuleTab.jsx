import { useMemo, useState } from 'react';
import {
  Box, Stack, Typography, Button, Chip, Alert, LinearProgress, Autocomplete,
  TextField, ToggleButton, ToggleButtonGroup, FormControl, InputLabel,
  Select, MenuItem, Tooltip, Paper, Divider,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
} from '@mui/material';
import PlayArrowOutlinedIcon from '@mui/icons-material/PlayArrowOutlined';
import VisibilityOutlinedIcon from '@mui/icons-material/VisibilityOutlined';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import api from '../../api.js';
import StatCard from '../../components/StatCard.jsx';
import GoldenRecordDialog from './GoldenRecordDialog.jsx';

// User-authored deduplication rule: multi-CDE selection, AND / OR combinator,
// + survivorship strategy. Replaces the old curated-rules library tab —
// stewards now compose their own rules from the project's actual CDEs.

const SURVIVORSHIP_OPTIONS = [
  {
    id: 'most_complete',
    label: 'Most complete row wins',
    hint: 'Keep the row with the fewest blanks. Other rows are dropped.',
  },
  {
    id: 'most_recent',
    label: 'Most recent row wins',
    hint: 'Keep the row with the latest value in the "recency" column you pick. Other rows are dropped.',
  },
  {
    id: 'field_level_merge',
    label: 'Per-field merge (Frankenstein)',
    hint: 'Build a single best row by taking each field from whichever member has it filled. The most-complete row becomes the survivor identity; missing fields are sourced from other group members.',
  },
];

const OPERATOR_HINT = {
  AND: 'Rows are duplicates only when EVERY selected CDE matches between them. Use for composite keys — e.g. name + PAN + GST.',
  OR:  'Rows are duplicates if ANY ONE selected CDE matches. Use when any one identifier shared = same entity — e.g. same PAN OR same Email.',
};

export default function CustomRuleTab({ allColumns }) {
  const [columns, setColumns] = useState([]);
  const [operator, setOperator] = useState('AND');
  const [strategy, setStrategy] = useState('most_complete');
  const [recencyColumn, setRecencyColumn] = useState('');
  const [scanBusy, setScanBusy] = useState(false);
  const [err, setErr] = useState('');
  const [scanResult, setScanResult] = useState(null);
  const [reviewGroup, setReviewGroup] = useState(null);

  // Recency column only matters for most_recent + field_level_merge strategies.
  const recencyApplies = strategy === 'most_recent' || strategy === 'field_level_merge';
  // Most-recent is broken without a recency column to sort by.
  const recencyRequired = strategy === 'most_recent';

  const ruleSummary = useMemo(() => {
    if (!columns.length) return 'Pick one or more critical data elements to begin.';
    if (columns.length === 1) return `Two records are duplicates when their ${columns[0]} is the same.`;
    const sep = operator === 'AND' ? ' AND ' : ' OR ';
    return `Two records are duplicates when ${columns.map((c) => `${c} matches`).join(sep)}.`;
  }, [columns, operator]);

  const survivorshipPayload = useMemo(() => {
    const cfg = { strategy };
    if (recencyApplies && recencyColumn) {
      cfg.recency_column = recencyColumn;
    }
    if (strategy === 'field_level_merge') {
      cfg.priority = recencyColumn ? ['most_complete', 'most_recent'] : ['most_complete'];
    }
    return cfg;
  }, [strategy, recencyColumn, recencyApplies]);

  const scan = async () => {
    setScanBusy(true);
    setErr('');
    setScanResult(null);
    try {
      const { data } = await api.post('/duplicates/custom/scan', {
        columns,
        operator,
        survivorship: survivorshipPayload,
      });
      setScanResult(data);
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Scan failed');
    } finally {
      setScanBusy(false);
    }
  };

  // Open the Golden Record dialog for a specific group. The backend
  // session can lose the scan cache between scan and review (hot-reload,
  // worker recycle, session expiry). Always re-run the scan first so the
  // server has the group cached when the dialog calls /golden.
  const openReview = async (groupId) => {
    setScanBusy(true);
    setErr('');
    try {
      // eslint-disable-next-line no-console
      console.log('[CustomRule] openReview start — re-scanning', { groupId, columns, operator, survivorshipPayload });
      const { data } = await api.post('/duplicates/custom/scan', {
        columns,
        operator,
        survivorship: survivorshipPayload,
      });
      // eslint-disable-next-line no-console
      console.log('[CustomRule] re-scan ok — groups:', data?.summaries?.map((s) => s.group_id));
      setReviewGroup({ dup_type: 'custom', group_id: groupId });
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('[CustomRule] re-scan failed', e?.response?.status, e?.response?.data);
      setErr(typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : 'Could not refresh scan');
    } finally {
      setScanBusy(false);
    }
  };

  return (
    <Box>
      {/* ── Authoring panel ──────────────────────────────────────────── */}
      <Paper variant="outlined" sx={{ p: 2.25, mb: 2.5 }}>
        <Typography
          sx={{
            fontFamily: "'Montserrat', sans-serif",
            fontSize: 17,
            fontWeight: 700,
            color: '#1A1A1A',
            mb: 0.5,
          }}
        >
          Custom deduplication rule
        </Typography>
        <Typography sx={{ fontSize: 13, color: '#555555', mb: 2 }}>
          Pick the critical data elements that identify the same entity in
          your dataset. Combine them with AND / OR, choose how the surviving
          record should be built, and run the rule. Works for employee,
          vendor, customer, product — or any master-data shape.
        </Typography>

        <Stack spacing={2.25}>
          <Autocomplete
            multiple
            size="small"
            options={allColumns || []}
            value={columns}
            onChange={(_, v) => setColumns(v)}
            disableCloseOnSelect
            renderInput={(params) => (
              <TextField
                {...params}
                label="Critical data elements"
                placeholder="e.g. first_name, last_name, email"
              />
            )}
          />

          <Box>
            <Stack direction="row" spacing={1.25} alignItems="center" sx={{ mb: 0.75 }}>
              <Typography sx={{ fontSize: 12.5, fontWeight: 700, color: '#1A1A1A', minWidth: 78 }}>
                Combine using
              </Typography>
              <ToggleButtonGroup
                exclusive
                size="small"
                value={operator}
                onChange={(_, v) => v && setOperator(v)}
                sx={{
                  '& .MuiToggleButton-root': {
                    textTransform: 'none', fontSize: 12, fontWeight: 700,
                    px: 1.75, py: 0.4, letterSpacing: '0.04em',
                  },
                }}
                disabled={columns.length < 2}
              >
                <ToggleButton value="AND">AND</ToggleButton>
                <ToggleButton value="OR">OR</ToggleButton>
              </ToggleButtonGroup>
              {columns.length < 2 && (
                <Typography sx={{ fontSize: 11.5, color: '#8A8A8A', fontStyle: 'italic' }}>
                  Pick 2+ CDEs to enable the combinator
                </Typography>
              )}
            </Stack>
            {columns.length >= 2 && (
              <Typography sx={{ fontSize: 11.5, color: '#555555', ml: '86px' }}>
                {OPERATOR_HINT[operator]}
              </Typography>
            )}
          </Box>

          <Divider sx={{ my: 0.5 }} />

          {/* ── Survivorship ────────────────────────────────────────── */}
          <Box>
            <Stack direction="row" alignItems="center" spacing={0.75} sx={{ mb: 0.75 }}>
              <Typography sx={{ fontSize: 12.5, fontWeight: 700, color: '#1A1A1A' }}>
                Which record survives?
              </Typography>
              <Tooltip
                title="When duplicates are found, this strategy decides which row to keep. The kept row becomes the 'golden record' and the rest are dropped after you click Apply on each group."
                arrow
              >
                <InfoOutlinedIcon sx={{ fontSize: 14, color: '#8A8A8A', cursor: 'help' }} />
              </Tooltip>
            </Stack>

            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems="stretch">
              <FormControl size="small" sx={{ minWidth: 260, flex: 1 }}>
                <InputLabel>Survivorship strategy</InputLabel>
                <Select
                  value={strategy}
                  label="Survivorship strategy"
                  onChange={(e) => setStrategy(e.target.value)}
                >
                  {SURVIVORSHIP_OPTIONS.map((o) => (
                    <MenuItem key={o.id} value={o.id}>{o.label}</MenuItem>
                  ))}
                </Select>
              </FormControl>

              {recencyApplies && (
                <FormControl size="small" sx={{ minWidth: 240, flex: 1 }}>
                  <InputLabel>
                    Recency column {recencyRequired ? '(required)' : '(optional)'}
                  </InputLabel>
                  <Select
                    value={recencyColumn}
                    label={`Recency column ${recencyRequired ? '(required)' : '(optional)'}`}
                    onChange={(e) => setRecencyColumn(e.target.value)}
                  >
                    <MenuItem value=""><em>— none —</em></MenuItem>
                    {(allColumns || []).map((c) => (
                      <MenuItem key={c} value={c}>{c}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
              )}
            </Stack>
            <Typography sx={{ fontSize: 11.5, color: '#555555', mt: 0.75 }}>
              {SURVIVORSHIP_OPTIONS.find((o) => o.id === strategy)?.hint}
            </Typography>
          </Box>

          <Alert
            severity={columns.length ? 'success' : 'info'}
            icon={<InfoOutlinedIcon fontSize="inherit" />}
            sx={{ bgcolor: columns.length ? '#F0FDF4' : '#F4ECF9' }}
          >
            {ruleSummary}
          </Alert>

          <Stack direction="row" justifyContent="flex-end">
            <Button
              variant="contained"
              startIcon={<PlayArrowOutlinedIcon />}
              onClick={scan}
              disabled={scanBusy || columns.length === 0 || (recencyRequired && !recencyColumn)}
              sx={{ fontWeight: 700, px: 2.5 }}
            >
              Run deduplication scan
            </Button>
          </Stack>
        </Stack>
      </Paper>

      {scanBusy && <LinearProgress sx={{ mb: 2 }} />}
      {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}

      {/* ── Results ─────────────────────────────────────────────────── */}
      {scanResult && (
        <>
          <Stack direction="row" alignItems="center" spacing={1.25} sx={{ mb: 1.25 }}>
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
              label={`${scanResult.operator} on ${scanResult.columns?.length ?? 0} CDE${(scanResult.columns?.length ?? 0) === 1 ? '' : 's'}`}
              sx={{ height: 20, fontSize: '0.7rem', bgcolor: '#F4ECF9', color: '#6A28A8' }}
            />
            <Chip
              size="small"
              label={`survivorship: ${scanResult.survivorship?.strategy || 'most_complete'}`}
              sx={{ height: 20, fontSize: '0.7rem', bgcolor: '#E6F0FC', color: '#1E3A8A' }}
            />
          </Stack>

          <Stack direction="row" spacing={1.5} sx={{ mb: 2 }}>
            <StatCard accent label="Duplicate groups" value={scanResult.total_groups} />
            <StatCard label="Rows affected" value={scanResult.total_rows} />
            <StatCard label="Operator" value={scanResult.operator} />
          </Stack>

          {scanResult.total_groups === 0 ? (
            <Alert severity="success">
              No duplicate groups matched this rule.
            </Alert>
          ) : (
            <TableContainer component={Paper} variant="outlined">
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 700, width: 80 }}>Group</TableCell>
                    <TableCell sx={{ fontWeight: 700, width: 100 }}>Members</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>Why these match</TableCell>
                    <TableCell sx={{ fontWeight: 700, width: 180 }} />
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(scanResult.summaries || []).map((g) => {
                    const memberCount = g.rows ?? g.row_count ?? g.indices?.length ?? 0;
                    const keyCols = Array.isArray(g.key_columns) ? g.key_columns.join(scanResult.operator === 'OR' ? ' OR ' : ' + ') : '';
                    return (
                      <TableRow key={g.group_id} hover>
                        <TableCell sx={{ fontFamily: 'ui-monospace, Menlo, monospace' }}>
                          #{g.group_id}
                        </TableCell>
                        <TableCell sx={{ fontWeight: 600 }}>{memberCount}</TableCell>
                        <TableCell>
                          {keyCols && (
                            <Typography sx={{ fontSize: '0.7rem', color: '#8A8A8A', fontFamily: 'ui-monospace, Menlo, monospace' }}>
                              {keyCols}
                            </Typography>
                          )}
                          <Typography
                            sx={{
                              fontSize: '0.82rem',
                              color: '#1A1A1A',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                              maxWidth: 480,
                            }}
                            title={g.representative}
                          >
                            {g.representative || <em style={{ color: '#8A8A8A' }}>—</em>}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Button
                            size="small"
                            variant="outlined"
                            startIcon={<VisibilityOutlinedIcon />}
                            onClick={() => openReview(g.group_id)}
                            disabled={scanBusy}
                          >
                            Review golden
                          </Button>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </>
      )}

      <GoldenRecordDialog
        open={!!reviewGroup}
        onClose={() => setReviewGroup(null)}
        dup_type={reviewGroup?.dup_type}
        group_id={reviewGroup?.group_id}
        rule_id={null}
        onApplied={() => {
          setReviewGroup(null);
          // After a group is applied (rows merged / dropped) re-run the
          // scan so the resolved group disappears from the list.
          scan();
        }}
      />
    </Box>
  );
}
