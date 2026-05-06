import { useEffect, useState } from 'react';
import {
  Box, Stack, Button, Typography, Alert, LinearProgress, Grid, Paper, Chip,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Divider,
  Tooltip,
} from '@mui/material';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import RefreshIcon from '@mui/icons-material/Refresh';
import DeleteIcon from '@mui/icons-material/Delete';
import DownloadIcon from '@mui/icons-material/Download';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import api from '../api.js';
import PageHeader from '../components/PageHeader.jsx';
import EmptyState from '../components/EmptyState.jsx';
import { useDataset } from '../context/DatasetContext.jsx';

// Seven DQ dimensions — single muted palette, no clashing pastels.
const DIMENSION_PALETTE = {
  Accuracy:                  { fg: '#1e3a8a', tint: '#eef2ff', dot: '#3b82f6' },
  Completeness:              { fg: '#14532d', tint: '#f0fdf4', dot: '#16a34a' },
  Consistency:               { fg: '#713f12', tint: '#fefce8', dot: '#ca8a04' },
  Validity:                  { fg: '#581c87', tint: '#faf5ff', dot: '#9333ea' },
  Uniqueness:                { fg: '#0c4a6e', tint: '#f0f9ff', dot: '#0284c7' },
  Timeliness:                { fg: '#134e4a', tint: '#f0fdfa', dot: '#0d9488' },
  'Cross-field Validation':  { fg: '#7c2d12', tint: '#fff7ed', dot: '#ea580c' },
};
const DIMENSION_FALLBACK = { fg: '#475569', tint: '#f1f5f9', dot: '#64748b' };
const dimensionStyle = (dim) => DIMENSION_PALETTE[dim] || DIMENSION_FALLBACK;

function MetricCard({ label, value, denominator, hint }) {
  return (
    <Paper sx={{ p: 2.5, textAlign: 'center', borderRadius: 2.5 }}>
      <Typography variant="caption" sx={{
        color: 'text.secondary', textTransform: 'uppercase', letterSpacing: 1, fontWeight: 500,
      }}>{label}</Typography>
      <Typography sx={{ fontSize: '1.8rem', fontWeight: 700, color: 'primary.main', mt: 0.75, lineHeight: 1.1 }}>
        {value}
        {denominator !== undefined && (
          <Typography component="span" sx={{
            fontSize: '1.05rem', fontWeight: 500, color: 'text.secondary', ml: 0.5,
          }}>
            / {denominator}
          </Typography>
        )}
      </Typography>
      {hint && (
        <Typography variant="caption" sx={{ color: 'text.disabled', display: 'block', mt: 0.25 }}>
          {hint}
        </Typography>
      )}
    </Paper>
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

  return (
    <>
      <PageHeader title="Rule Generator" subtitle="AI-Powered Validation Rule Generation" />

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={4}>
          {!generated ? (
            <Button fullWidth size="large" variant="contained" startIcon={<AutoAwesomeIcon />}
              onClick={generate} disabled={busy}>
              {busy ? 'Analyzing data with comprehensive engine…' : 'Generate AI Validation Rules'}
            </Button>
          ) : (
            <Alert severity="success" sx={{ height: '100%' }}>Rules Generated</Alert>
          )}
        </Grid>
        <Grid item xs={12} md={4}>
          {generated && (
            <Button fullWidth size="large" variant="outlined" startIcon={<RefreshIcon />}
              onClick={regenerate} disabled={busy}>Regenerate Rules</Button>
          )}
        </Grid>
        <Grid item xs={12} md={4}>
          {generated && (
            <Button fullWidth size="large" variant="outlined" color="error"
              startIcon={<DeleteIcon />} onClick={clear} disabled={busy}>Clear Rules</Button>
          )}
        </Grid>
      </Grid>

      {busy && <LinearProgress sx={{ mb: 2 }} />}
      {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}

      <Divider sx={{ my: 2 }} />

      {generated && rules.length > 0 ? (
        <>
          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid item xs={4}><MetricCard label="Total Rules" value={stats.total_rules} /></Grid>
            <Grid item xs={4}><MetricCard label="Columns Covered" value={stats.columns_covered} /></Grid>
            <Grid item xs={4}>
              <MetricCard
                label="DQ Dimensions"
                value={stats.dq_dimensions}
                denominator={7}
                hint="of 7 standard dimensions used"
              />
            </Grid>
          </Grid>

          <Divider sx={{ my: 2 }} />

          <Stack direction="row" alignItems="baseline" justifyContent="space-between" sx={{ mb: 1.5 }}>
            <Typography variant="h6">Data Quality Rules</Typography>
            <Typography variant="caption" color="text.secondary">
              {rules.length} rules · {stats.columns_covered} columns · {stats.dq_dimensions} dimensions
            </Typography>
          </Stack>
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
              '& tbody tr:hover': { bgcolor: 'rgba(91, 26, 120, 0.03)' },
              '& tbody tr:nth-of-type(even)': { bgcolor: '#fafafa' },
              '& tbody tr:nth-of-type(even):hover': { bgcolor: 'rgba(91, 26, 120, 0.04)' },
            }}>
              <TableHead>
                <TableRow sx={{
                  '& th': {
                    bgcolor: '#f8fafc',
                    color: 'text.secondary',
                    fontWeight: 600,
                    fontSize: '0.72rem',
                    letterSpacing: '0.04em',
                    textTransform: 'uppercase',
                    py: 1.25,
                    borderBottom: '1px solid',
                    borderColor: 'divider',
                  },
                }}>
                  <TableCell sx={{ width: 56 }}>#</TableCell>
                  <TableCell>Column</TableCell>
                  <TableCell>Business Field</TableCell>
                  <TableCell sx={{ width: 110 }}>Source</TableCell>
                  <TableCell sx={{ width: 150 }}>Dimension</TableCell>
                  <TableCell>Data Quality Rule</TableCell>
                  <TableCell>Regex Pattern</TableCell>
                  <TableCell align="right" sx={{ width: 90 }}>Issues</TableCell>
                  <TableCell sx={{ minWidth: 260 }}>Result</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {rules.map((r, i) => {
                  const issues = Number(r['Issues Found']) || 0;
                  const example = String(r['Issues Found Example'] || '');
                  const isCrossField = r.Dimension === 'Cross-field Validation';
                  // For cross-field rules: "manual review" means the
                  // executor couldn't evaluate it. Anything else means
                  // it ran and we should display real numbers.
                  const crossFieldUnevaluated = isCrossField && example.toLowerCase().includes('manual review');
                  const validationExpr = String(r['Validation Expression'] || '');
                  const regexCellContent = isCrossField ? validationExpr : String(r['Regex Pattern'] || '');
                  const isOk = !example || example.startsWith('All values valid');
                  const dim = dimensionStyle(r.Dimension);
                  const src = sourceChipProps(r['Rule Source']);
                  return (
                    <TableRow key={i} sx={{ '& td': { py: 1.1, fontSize: '0.84rem' } }}>
                      <TableCell sx={{ color: 'text.secondary', fontVariantNumeric: 'tabular-nums' }}>
                        {r['S.No']}
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
                      <TableCell sx={{ maxWidth: 220 }}>
                        {regexCellContent ? (
                          <Tooltip title={regexCellContent} placement="top">
                            <Box component="code" sx={{
                              display: 'inline-block',
                              maxWidth: '100%',
                              px: 0.75,
                              py: 0.25,
                              borderRadius: 0.75,
                              bgcolor: '#f1f5f9',
                              color: '#475569',
                              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                              fontSize: '0.72rem',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                              verticalAlign: 'middle',
                            }}>
                              {regexCellContent}
                            </Box>
                          </Tooltip>
                        ) : (
                          <Typography variant="caption" sx={{ color: 'text.disabled' }}>—</Typography>
                        )}
                      </TableCell>
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
                    </TableRow>
                  );
                })}
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
    </>
  );
}
