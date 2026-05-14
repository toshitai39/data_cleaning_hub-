import { useEffect, useMemo, useState } from 'react';
import {
  Box, Stack, Button, Typography, Alert, LinearProgress, Grid, Paper, Chip,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Divider,
  Tooltip, Tabs, Tab, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, MenuItem, IconButton, Autocomplete,
  ToggleButton, ToggleButtonGroup,
} from '@mui/material';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import RefreshIcon from '@mui/icons-material/Refresh';
import DeleteIcon from '@mui/icons-material/Delete';
import DownloadIcon from '@mui/icons-material/Download';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import AddCircleOutlineIcon from '@mui/icons-material/AddCircleOutline';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import api from '../api.js';
import PageHeader from '../components/PageHeader.jsx';
import ActionButton from '../components/ActionButton.jsx';
import EmptyState from '../components/EmptyState.jsx';
import { useDataset } from '../context/DatasetContext.jsx';

// Seven DQ dimensions — single muted palette, no clashing pastels.
// Pre-rename keys (Consistency, Validity) are kept as aliases so rules
// persisted before the 2026-05 rename still render with the same color.
const DIMENSION_PALETTE = {
  Accuracy:                  { fg: '#1e3a8a', tint: '#eef2ff', dot: '#3b82f6' },
  Completeness:              { fg: '#14532d', tint: '#f0fdf4', dot: '#16a34a' },
  Standardisation:           { fg: '#713f12', tint: '#fefce8', dot: '#ca8a04' },
  Validation:                { fg: '#581c87', tint: '#faf5ff', dot: '#9333ea' },
  Uniqueness:                { fg: '#0c4a6e', tint: '#f0f9ff', dot: '#0284c7' },
  Timeliness:                { fg: '#134e4a', tint: '#f0fdfa', dot: '#0d9488' },
  'Cross-field Validation':  { fg: '#7c2d12', tint: '#fff7ed', dot: '#ea580c' },
  Consistency:               { fg: '#713f12', tint: '#fefce8', dot: '#ca8a04' },
  Validity:                  { fg: '#581c87', tint: '#faf5ff', dot: '#9333ea' },
};
const DIMENSION_FALLBACK = { fg: '#475569', tint: '#f1f5f9', dot: '#64748b' };
const dimensionStyle = (dim) => DIMENSION_PALETTE[dim] || DIMENSION_FALLBACK;

function MetricCard({ label, value, denominator, hint }) {
  return (
    <Box sx={{
      bgcolor: '#FBFAFC',
      border: '1px solid #E7E6E6',
      borderRadius: 1.5,
      px: 2.25,
      py: 2,
    }}>
      <Typography sx={{
        fontFamily: "'Open Sans', sans-serif",
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: '0.1em',
        color: '#8A8A8A',
        textTransform: 'uppercase',
        mb: 0.75,
      }}>
        {label}
      </Typography>
      <Typography sx={{
        fontFamily: "'Montserrat', sans-serif",
        fontSize: 26,
        fontWeight: 700,
        color: '#1A1A1A',
        lineHeight: 1,
      }}>
        {value}
        {denominator !== undefined && (
          <Typography component="span" sx={{
            fontSize: 15, fontWeight: 500, color: '#8A8A8A', ml: 0.5,
          }}>
            / {denominator}
          </Typography>
        )}
      </Typography>
      {hint && (
        <Typography sx={{ fontSize: 12, color: '#8A8A8A', mt: 0.75 }}>
          {hint}
        </Typography>
      )}
    </Box>
  );
}

export default function RuleGenerator() {
  const { state } = useDataset();
  const [llm, setLlm] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [generated, setGenerated] = useState(false);
  const [rules, setRules] = useState([]);
  const [stats, setStats] = useState({ total_rules: 0, columns_covered: 0, dq_dimensions: 0 });
  const [scope, setScope] = useState({ selected: [], all: [], explicit: false });
  const [glossary, setGlossary] = useState({ generated: false, count: 0 });
  const [activeDim, setActiveDim] = useState('All');
  const [customOpen, setCustomOpen] = useState(false);
  const [customBusy, setCustomBusy] = useState(false);
  const [customErr, setCustomErr] = useState('');
  const blankCustom = {
    dimension: 'Validation',
    column: '',
    columns: [],
    operator: 'AND',
    data_quality_rule: '',
    regex_pattern: '',
    validation_expression: '',
  };
  const [customForm, setCustomForm] = useState(blankCustom);

  // Capability map — which dimensions support multi-CDE + AND/OR, and
  // what the operator actually means for each. Drives the dialog UI and
  // is mirrored on the backend (single source of truth in spirit).
  // - multi: dimension can target N CDEs in one rule
  // - operator: AND/OR is meaningful (vs ignored)
  // - opHint: short copy shown under the toggle, dimension-specific so
  //   stewards see exactly what the operator will compute
  const DIM_CAPS = {
    'Validation':              { multi: true,  operator: true,  opHint: { AND: 'Every selected CDE must match the regex / rule.', OR: 'At least one selected CDE must match.' } },
    'Completeness':            { multi: true,  operator: true,  opHint: { AND: 'All selected CDEs must be non-null on every row.', OR: 'At least one selected CDE must be non-null on every row.' } },
    'Uniqueness':              { multi: true,  operator: true,  opHint: { AND: 'The selected CDEs must be unique as a composite key (tuple).', OR: 'Each selected CDE must be independently unique.' } },
    'Standardisation':         { multi: false, operator: false },
    'Accuracy':                { multi: false, operator: false },
    'Timeliness':              { multi: false, operator: false },
    'Cross-field Validation':  { multi: true,  operator: false }, // natural-language; engine resolves
  };

  useEffect(() => {
    api.get('/rule-generator/llm-status').then((r) => setLlm(r.data)).catch(() => setLlm({ configured: false }));
    if (state.loaded) {
      api.get('/rule-generator/rules').then((r) => {
        if (r.data.generated) {
          setRules(r.data.rules);
          setStats({
            total_rules: r.data.total_rules,
            columns_covered: r.data.columns_covered,
            dq_dimensions: r.data.dq_dimensions,
          });
          setGenerated(true);
        }
      }).catch(() => {});
      api
        .get('/data/columns-of-interest')
        .then((r) => setScope({
          selected: r.data.selected || [],
          all: r.data.all || [],
          explicit: !!r.data.explicit,
        }))
        .catch(() => {});
      api
        .get('/profile/semantic-glossary')
        .then((r) => setGlossary({
          generated: !!r.data.generated,
          count: (r.data.entries || []).length,
        }))
        .catch(() => {});
    }
  }, [state.loaded]);

  const generate = async () => {
    setBusy(true); setErr('');
    try {
      const { data } = await api.post('/rule-generator/generate');
      setRules(data.rules);
      setStats({
        total_rules: data.total_rules,
        columns_covered: data.columns_covered,
        dq_dimensions: data.dq_dimensions,
      });
      setGenerated(true);
    } catch (e) { setErr(e?.response?.data?.detail || 'Generation failed'); }
    finally { setBusy(false); }
  };

  const regenerate = async () => {
    setBusy(true); setErr('');
    try {
      await api.post('/rule-generator/regenerate');
      setGenerated(false);
      setRules([]);
      setStats({ total_rules: 0, columns_covered: 0, dq_dimensions: 0 });
    } catch (e) { setErr(e?.response?.data?.detail || 'Failed'); }
    finally { setBusy(false); }
  };

  const clear = async () => {
    setBusy(true); setErr('');
    try {
      await api.post('/rule-generator/clear');
      setGenerated(false);
      setRules([]);
      setStats({ total_rules: 0, columns_covered: 0, dq_dimensions: 0 });
    } catch (e) { setErr(e?.response?.data?.detail || 'Failed'); }
    finally { setBusy(false); }
  };

  const openCustom = () => {
    setCustomForm(blankCustom);
    setCustomErr('');
    setCustomOpen(true);
  };

  const saveCustom = async () => {
    setCustomBusy(true); setCustomErr('');
    try {
      const caps = DIM_CAPS[customForm.dimension] || { multi: false, operator: false };
      const isCross = customForm.dimension === 'Cross-field Validation';
      const cols = caps.multi ? (customForm.columns || []) : [];
      const single = !caps.multi ? (customForm.column || '') : '';
      // Multi-CDE rules ship `columns` + operator; single-CDE ship `column`.
      // Cross-field still uses `columns` but operator is irrelevant — the
      // natural-language resolver decides the combinator.
      const payload = {
        dimension: customForm.dimension,
        data_quality_rule: customForm.data_quality_rule,
        regex_pattern: customForm.regex_pattern || '',
        validation_expression: '',
        ...(caps.multi
          ? { columns: cols, ...(caps.operator ? { operator: customForm.operator } : {}) }
          : { column: single }),
      };
      // When the steward picks multi-CDE but only one CDE on a dimension
      // that supports multi, treat it as a single-column rule — operator
      // is meaningless and the backend handles it cleanly.
      if (caps.multi && !isCross && cols.length === 1) {
        payload.column = cols[0];
        delete payload.columns;
        delete payload.operator;
      }
      const { data } = await api.post('/rule-generator/rules/custom', payload);
      setRules(data.rules);
      setStats((s) => ({ ...s, total_rules: data.total_rules }));
      setGenerated(true);
      setCustomOpen(false);
    } catch (e) {
      setCustomErr(e?.response?.data?.detail || 'Could not save custom rule');
    } finally { setCustomBusy(false); }
  };

  const deleteRule = async (ruleIdx) => {
    try {
      const { data } = await api.delete(`/rule-generator/rules/${ruleIdx}`);
      setRules(data.rules);
      setStats((s) => ({ ...s, total_rules: data.total_rules }));
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Could not delete rule');
    }
  };

  const downloadBlob = async (path, defaultName) => {
    try {
      const res = await api.post(path, null, { responseType: 'blob' });
      const cd = res.headers['content-disposition'] || '';
      const m = cd.match(/filename="?([^"]+)"?/);
      const filename = m ? m[1] : defaultName;
      const url = URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url; a.download = filename; a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Export failed');
    }
  };

  const sourceChipProps = (val) => {
    if (val === 'Rules from Existing Sheet') {
      return { label: 'From Sheet', sx: { bgcolor: '#f0fdf4', color: '#14532d', borderColor: '#bbf7d0' } };
    }
    if (val === 'Generated by AI') {
      return { label: 'AI', sx: { bgcolor: '#faf5ff', color: '#581c87', borderColor: '#e9d5ff' } };
    }
    if (val === 'Custom') {
      return { label: 'Custom', sx: { bgcolor: '#fff7ed', color: '#9a3412', borderColor: '#fed7aa' } };
    }
    return { label: val || '—', sx: {} };
  };

  if (!state.loaded) {
    return (
      <>
        <PageHeader title="Rule Generator" subtitle="AI-Powered Validation Rule Generation" />
        <Alert severity="warning">Please load data first before generating rules.</Alert>
        <Alert severity="info" sx={{ mt: 1 }}>Go to the 'Load Data' tab and upload your file.</Alert>
        <Box sx={{ mt: 2 }}><EmptyState /></Box>
      </>
    );
  }

  if (llm && !llm.configured) {
    return (
      <>
        <PageHeader title="Rule Generator" subtitle="AI-Powered Validation Rule Generation" />
        <Alert severity="error">
          Azure OpenAI not configured. Missing: {(llm.missing || []).join(', ')}
        </Alert>
        <Alert severity="info" sx={{ mt: 1 }}>
          Add these to a <code>.env</code> file in the project root (it is gitignored — never committed):
        </Alert>
        <Paper sx={{ mt: 2, p: 2, fontFamily: 'monospace', fontSize: '0.85rem' }}>
{`AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
AZURE_OPENAI_KEY="your-api-key"
AZURE_OPENAI_DEPLOYMENT="gpt-4o-mini"
AZURE_OPENAI_API_VERSION="2025-01-01-preview"
AZURE_OPENAI_MAX_RPM=60`}
        </Paper>
      </>
    );
  }

  const scopeIsRestricted = scope.explicit && scope.selected.length !== scope.all.length;

  // Group rules by dimension for the dimension-tab filter — the client
  // doesn't want to see all 7 dimensions at once, just one at a time.
  const dimOrder = useMemo(
    () => [
      'Accuracy', 'Completeness', 'Standardisation', 'Validation',
      'Uniqueness', 'Timeliness', 'Cross-field Validation',
    ],
    [],
  );
  const dimCounts = useMemo(() => {
    const counts = new Map();
    for (const r of rules) {
      const d = r.Dimension || 'Other';
      counts.set(d, (counts.get(d) || 0) + 1);
    }
    return counts;
  }, [rules]);
  const dimsWithRules = useMemo(
    () => dimOrder.filter((d) => dimCounts.get(d) > 0),
    [dimOrder, dimCounts],
  );
  const filteredRules = useMemo(() => {
    if (activeDim === 'All') return rules;
    return rules.filter((r) => (r.Dimension || '') === activeDim);
  }, [rules, activeDim]);

  return (
    <>
      <PageHeader title="Rule Generator" subtitle="AI-Powered Validation Rule Generation" />

      {scope.all.length > 0 && (
        <Alert
          severity={scopeIsRestricted ? 'info' : 'success'}
          icon={<InfoOutlinedIcon fontSize="inherit" />}
          sx={{ mb: 2 }}
        >
          Scope: <b>{scope.selected.length}</b> / <b>{scope.all.length}</b> critical data elements
          {' · '}
          Glossary: <b>{glossary.generated ? `${glossary.count} entries` : 'not generated'}</b>
        </Alert>
      )}

      <Grid container spacing={1.5} sx={{ mb: 2.5 }}>
        <Grid item xs={12} md={3}>
          {!generated ? (
            <Button
              fullWidth
              variant="contained"
              startIcon={<AutoAwesomeIcon />}
              onClick={generate}
              disabled={busy}
              sx={{ py: 1.25, fontSize: 14, fontWeight: 700 }}
            >
              {busy ? 'Analyzing…' : 'Generate Rules'}
            </Button>
          ) : (
            <ActionButton tone="success" startIcon={<CheckCircleOutlineIcon />} disabled>
              Rules Generated
            </ActionButton>
          )}
        </Grid>
        <Grid item xs={12} md={3}>
          <ActionButton
            startIcon={<AddCircleOutlineIcon />}
            onClick={openCustom}
            disabled={busy || !state.loaded}
          >
            Add Custom Rule
          </ActionButton>
        </Grid>
        <Grid item xs={12} md={3}>
          <ActionButton
            startIcon={<RefreshIcon />}
            onClick={regenerate}
            disabled={busy || !generated}
          >
            Regenerate Rules
          </ActionButton>
        </Grid>
        <Grid item xs={12} md={3}>
          <ActionButton
            tone="danger"
            startIcon={<DeleteIcon />}
            onClick={clear}
            disabled={busy || !generated}
          >
            Clear Rules
          </ActionButton>
        </Grid>
      </Grid>

      {busy && <LinearProgress sx={{ mb: 2 }} />}
      {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}

      {generated && rules.length > 0 ? (
        <>
          <Grid container spacing={1.5} sx={{ mb: 2 }}>
            <Grid item xs={4}><MetricCard label="Total Rules" value={stats.total_rules} /></Grid>
            <Grid item xs={4}><MetricCard label="Critical Data Elements Covered" value={stats.columns_covered} /></Grid>
            <Grid item xs={4}>
              <MetricCard
                label="DQ Dimensions"
                value={stats.dq_dimensions}
                denominator={7}
                hint="of 7 standard dimensions used"
              />
            </Grid>
          </Grid>

          <Box sx={{ borderTop: '1px solid #E7E6E6', pt: 3, mt: 3 }}>
            <Stack
              direction="row"
              alignItems="baseline"
              justifyContent="space-between"
              sx={{ mb: 1.5 }}
            >
              <Typography
                sx={{
                  fontFamily: "'Montserrat', sans-serif",
                  fontSize: 22,
                  fontWeight: 700,
                  color: '#1A1A1A',
                }}
              >
                Data Quality Rules
              </Typography>
              <Typography sx={{ fontSize: 12, color: '#8A8A8A', fontWeight: 500 }}>
                {filteredRules.length} of {rules.length} rules
                {activeDim !== 'All' && ` · viewing ${activeDim}`}
              </Typography>
            </Stack>
          </Box>

          <Box sx={{
            borderBottom: 1, borderColor: 'divider', mb: 1.5,
          }}>
            <Tabs
              value={activeDim}
              onChange={(_, v) => setActiveDim(v)}
              variant="scrollable"
              scrollButtons="auto"
              TabIndicatorProps={{
                sx: {
                  height: 3,
                  borderRadius: 2,
                  bgcolor: activeDim === 'All'
                    ? 'primary.main'
                    : dimensionStyle(activeDim).dot,
                },
              }}
              sx={{ minHeight: 40, '& .MuiTab-root': { minHeight: 40, py: 1, textTransform: 'none' } }}
            >
              <Tab
                value="All"
                label={
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                    <Typography variant="body2" sx={{ fontWeight: activeDim === 'All' ? 700 : 500 }}>
                      All
                    </Typography>
                    <Chip
                      size="small"
                      label={rules.length}
                      sx={{ height: 18, fontSize: '0.7rem', fontWeight: 600 }}
                    />
                  </Box>
                }
              />
              {dimsWithRules.map((d) => {
                const style = dimensionStyle(d);
                const active = activeDim === d;
                return (
                  <Tab
                    key={d}
                    value={d}
                    label={
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                        <Box sx={{
                          width: 8, height: 8, borderRadius: '50%', bgcolor: style.dot,
                        }} />
                        <Typography
                          variant="body2"
                          sx={{ fontWeight: active ? 700 : 500, color: active ? style.fg : 'text.primary' }}
                        >
                          {d}
                        </Typography>
                        <Chip
                          size="small"
                          label={dimCounts.get(d) || 0}
                          sx={{
                            height: 18,
                            fontSize: '0.7rem',
                            fontWeight: 600,
                            bgcolor: active ? style.tint : 'rgba(0,0,0,0.06)',
                            color: active ? style.fg : 'text.secondary',
                          }}
                        />
                      </Box>
                    }
                  />
                );
              })}
            </Tabs>
          </Box>
          <TableContainer
            component={Paper}
            sx={{
              maxHeight: 700,
              borderRadius: 2,
              border: '1px solid',
              borderColor: 'divider',
              boxShadow: 'none',
            }}
          >
            <Table stickyHeader size="small" sx={{
              '& td, & th': { borderColor: 'divider' },
              '& tbody tr:hover': { bgcolor: '#F7F5FA' },
            }}>
              <TableHead>
                <TableRow sx={{
                  '& th': {
                    bgcolor: '#FBFAFC',
                    color: '#8A8A8A',
                    fontWeight: 700,
                    fontSize: '0.72rem',
                    letterSpacing: '0.08em',
                    textTransform: 'uppercase',
                    py: 1.25,
                    borderBottom: '1px solid #E7E6E6',
                  },
                }}>
                  <TableCell sx={{ width: 56 }}>#</TableCell>
                  <TableCell>Critical Data Element</TableCell>
                  <TableCell>Business Field</TableCell>
                  <TableCell sx={{ width: 110 }}>Source</TableCell>
                  <TableCell sx={{ width: 150 }}>Dimension</TableCell>
                  <TableCell>Data Quality Rule</TableCell>
                  <TableCell align="right" sx={{ width: 90 }}>Issues</TableCell>
                  <TableCell sx={{ minWidth: 260 }}>Result</TableCell>
                  <TableCell sx={{ width: 56 }} />
                </TableRow>
              </TableHead>
              <TableBody>
                {filteredRules.map((r, i) => {
                  const issues = Number(r['Issues Found']) || 0;
                  const example = String(r['Issues Found Example'] || '');
                  const isCrossField = r.Dimension === 'Cross-field Validation';
                  // For cross-field rules: "manual review" means the
                  // executor couldn't evaluate it. Anything else means
                  // it ran and we should display real numbers.
                  const crossFieldUnevaluated = isCrossField && example.toLowerCase().includes('manual review');
                  const isOk = !example || example.startsWith('All values valid');
                  const dim = dimensionStyle(r.Dimension);
                  const src = sourceChipProps(r['Rule Source']);
                  return (
                    <TableRow key={r['S.No'] ?? i} sx={{ '& td': { py: 1.1, fontSize: '0.84rem' } }}>
                      <TableCell sx={{ color: 'text.secondary', fontVariantNumeric: 'tabular-nums' }}>
                        {i + 1}
                      </TableCell>
                      <TableCell sx={{ fontWeight: 500 }}>{r['Column']}</TableCell>
                      <TableCell sx={{ color: 'text.secondary' }}>{r['Business Field']}</TableCell>
                      <TableCell>
                        <Chip
                          size="small"
                          variant="outlined"
                          label={src.label}
                          sx={{
                            height: 22,
                            fontSize: '0.7rem',
                            fontWeight: 600,
                            borderRadius: 1,
                            ...src.sx,
                          }}
                        />
                      </TableCell>
                      <TableCell>
                        <Box sx={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 0.75,
                          px: 1,
                          py: 0.25,
                          borderRadius: 1,
                          bgcolor: dim.tint,
                          color: dim.fg,
                          fontSize: '0.74rem',
                          fontWeight: 600,
                        }}>
                          <Box sx={{
                            width: 6, height: 6, borderRadius: '50%', bgcolor: dim.dot,
                          }} />
                          {r.Dimension}
                        </Box>
                      </TableCell>
                      <TableCell sx={{ color: 'text.primary' }}>{r['Data Quality Rule']}</TableCell>
                      <TableCell align="right" sx={{
                        fontVariantNumeric: 'tabular-nums',
                        fontWeight: 600,
                        color: crossFieldUnevaluated
                          ? 'text.disabled'
                          : issues > 0 ? 'error.main' : 'text.disabled',
                      }}>
                        {crossFieldUnevaluated ? '—' : issues}
                      </TableCell>
                      <TableCell sx={{ minWidth: 260, maxWidth: 360 }}>
                        <Stack direction="row" spacing={0.75} alignItems="flex-start">
                          {crossFieldUnevaluated ? (
                            <InfoOutlinedIcon sx={{ fontSize: 16, color: 'info.main', mt: '3px', flexShrink: 0 }} />
                          ) : isOk ? (
                            <CheckCircleOutlineIcon sx={{ fontSize: 16, color: 'success.main', mt: '3px', flexShrink: 0 }} />
                          ) : (
                            <ErrorOutlineIcon sx={{ fontSize: 16, color: 'warning.main', mt: '3px', flexShrink: 0 }} />
                          )}
                          <Typography variant="body2" sx={{
                            color: crossFieldUnevaluated ? 'text.secondary' : isOk ? 'text.secondary' : 'text.primary',
                            fontSize: '0.8rem',
                            lineHeight: 1.5,
                            overflowWrap: 'anywhere',
                            wordBreak: 'normal',
                          }}>
                            {crossFieldUnevaluated
                              ? 'Cross-field — manual review'
                              : isOk ? 'All values valid' : example}
                          </Typography>
                        </Stack>
                      </TableCell>
                      <TableCell sx={{ width: 56 }}>
                        <Tooltip title="Delete rule">
                          <IconButton
                            size="small"
                            onClick={() => {
                              // map back to absolute index in `rules`
                              const absoluteIdx = rules.indexOf(r);
                              if (absoluteIdx >= 0) deleteRule(absoluteIdx);
                            }}
                          >
                            <DeleteOutlineIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  );
                })}
                {filteredRules.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={8} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                      No {activeDim === 'All' ? '' : `${activeDim} `}rules to show.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>

          <Divider sx={{ my: 3 }} />

          <Typography variant="h6" gutterBottom>Export Rules</Typography>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ maxWidth: 700 }}>
            <Button variant="outlined" startIcon={<DownloadIcon />}
              onClick={() => downloadBlob('/rule-generator/export/excel', 'rules.xlsx')}>
              Download as Excel
            </Button>
            <Button variant="outlined" startIcon={<DownloadIcon />}
              onClick={() => downloadBlob('/rule-generator/export/pdf', 'rules.pdf')}>
              Download DQ Report PDF
            </Button>
          </Stack>
        </>
      ) : (
        !busy && (
          <Alert severity="info">Click 'Generate AI Validation Rules' to start</Alert>
        )
      )}

      <Dialog open={customOpen} onClose={() => setCustomOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Add custom rule</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              size="small"
              label="Dimension"
              value={customForm.dimension}
              onChange={(e) => setCustomForm((f) => ({ ...f, dimension: e.target.value }))}
              fullWidth
            >
              {['Accuracy', 'Completeness', 'Standardisation', 'Validation',
                'Uniqueness', 'Timeliness', 'Cross-field Validation'].map((d) => (
                <MenuItem key={d} value={d}>{d}</MenuItem>
              ))}
            </TextField>

            {(() => {
              const caps = DIM_CAPS[customForm.dimension] || { multi: false, operator: false };
              if (!caps.multi) {
                return (
                  <Autocomplete
                    size="small"
                    options={scope.all}
                    value={customForm.column || null}
                    onChange={(_, v) => setCustomForm((f) => ({ ...f, column: v || '' }))}
                    renderInput={(params) => (
                      <TextField {...params} label="Critical data element" />
                    )}
                  />
                );
              }
              // Multi-CDE picker + (optionally) AND/OR operator
              const cols = customForm.columns || [];
              const showOp = caps.operator && cols.length >= 2;
              return (
                <>
                  <Autocomplete
                    multiple
                    size="small"
                    options={scope.all}
                    value={cols}
                    onChange={(_, v) => setCustomForm((f) => ({ ...f, columns: v }))}
                    renderInput={(params) => (
                      <TextField
                        {...params}
                        label={
                          customForm.dimension === 'Cross-field Validation'
                            ? 'Critical data elements (pick 2 or more)'
                            : 'Critical data element(s) — pick 1 or more'
                        }
                      />
                    )}
                  />
                  {showOp && (
                    <Box>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Typography sx={{ fontSize: 12.5, fontWeight: 600, color: '#1A1A1A', minWidth: 78 }}>
                          Combine using
                        </Typography>
                        <ToggleButtonGroup
                          exclusive
                          size="small"
                          value={customForm.operator}
                          onChange={(_, v) => v && setCustomForm((f) => ({ ...f, operator: v }))}
                          sx={{
                            '& .MuiToggleButton-root': {
                              textTransform: 'none', fontSize: 12, fontWeight: 700,
                              px: 1.75, py: 0.4, letterSpacing: '0.04em',
                            },
                          }}
                        >
                          <ToggleButton value="AND">AND</ToggleButton>
                          <ToggleButton value="OR">OR</ToggleButton>
                        </ToggleButtonGroup>
                      </Stack>
                      {caps.opHint && (
                        <Typography sx={{ fontSize: 11.5, color: '#7C7892', mt: 0.6, ml: '86px' }}>
                          {caps.opHint[customForm.operator] || ''}
                        </Typography>
                      )}
                    </Box>
                  )}
                </>
              );
            })()}

            <TextField
              size="small"
              label="Rule text"
              placeholder="e.g. email must contain a single @ symbol"
              value={customForm.data_quality_rule}
              onChange={(e) => setCustomForm((f) => ({ ...f, data_quality_rule: e.target.value }))}
              fullWidth
              multiline
              minRows={2}
            />

            {customForm.dimension === 'Cross-field Validation' && (
              <Alert severity="info" icon={<InfoOutlinedIcon fontSize="inherit" />}>
                Write the rule in natural language above. The engine will
                resolve it — composite uniqueness, conditional presence,
                prefix derivation, and arithmetic identities are all
                recognised automatically. Anything outside those falls back
                to the AI translator.
              </Alert>
            )}

            {customErr && <Alert severity="error">{customErr}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCustomOpen(false)} disabled={customBusy}>Cancel</Button>
          <Button variant="contained" onClick={saveCustom} disabled={customBusy}>
            {customBusy ? 'Saving…' : 'Save rule'}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
