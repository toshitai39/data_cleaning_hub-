import { useEffect, useMemo, useState } from 'react';
import {
  Box, Stack, Button, Alert, Typography, LinearProgress, Chip, Checkbox,
  FormControlLabel, Select, MenuItem, OutlinedInput, FormControl, InputLabel,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper, Grid,
} from '@mui/material';
import api from '../../api.js';
import PlotlyChart from './PlotlyChart.jsx';

const DIMENSION_BG = {
  Accuracy: '#dbeafe', Completeness: '#dcfce7', Consistency: '#fef3c7',
  Validity: '#fce7f3', Uniqueness: '#f3e8ff', Timeliness: '#ccfbf1',
  Integrity: '#fee2e2', Conformity: '#e0e7ff', Reliability: '#ffedd5',
  Relevance: '#ecfccb', Precision: '#fae8ff', Accessibility: '#e0f2fe',
  'Character Length': '#fde68a',
};
const DIMENSION_FG = {
  Accuracy: '#1e40af', Completeness: '#166534', Consistency: '#92400e',
  Validity: '#9d174d', Uniqueness: '#6b21a8', Timeliness: '#0f766e',
  Integrity: '#991b1b', Conformity: '#3730a3', Reliability: '#9a3412',
  Relevance: '#3f6212', Precision: '#86198f', Accessibility: '#075985',
  'Character Length': '#92400e',
};

export default function AiRulesTab() {
  const [llm, setLlm] = useState(null);
  const [rules, setRules] = useState([]);
  const [generated, setGenerated] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [showClient, setShowClient] = useState(true);
  const [showAi, setShowAi] = useState(true);
  const [selectedDims, setSelectedDims] = useState([]);

  useEffect(() => {
    api.get('/profile/llm-status').then((r) => setLlm(r.data)).catch(() => setLlm({ configured: false }));
    api.get('/profile/ai-rules').then((r) => {
      if (r.data.generated) {
        setRules(r.data.rules);
        setGenerated(true);
        const dims = [...new Set(r.data.rules.map((x) => x.Dimension))];
        setSelectedDims(dims);
      }
    }).catch(() => {});
  }, []);

  const generate = async () => {
    setBusy(true); setErr('');
    try {
      const { data } = await api.post('/profile/ai-rules/generate');
      setRules(data.rules);
      setGenerated(true);
      const dims = [...new Set(data.rules.map((x) => x.Dimension))];
      setSelectedDims(dims);
    } catch (e) { setErr(e?.response?.data?.detail || 'Generation failed'); }
    finally { setBusy(false); }
  };

  const clear = async () => {
    setBusy(true); setErr('');
    try {
      await api.post('/profile/ai-rules/clear');
      setRules([]); setGenerated(false); setSelectedDims([]);
    } catch (e) { setErr(e?.response?.data?.detail || 'Clear failed'); }
    finally { setBusy(false); }
  };

  const filtered = useMemo(() => {
    let out = rules;
    if (selectedDims.length > 0) {
      out = out.filter((r) => selectedDims.includes(r.Dimension));
    }
    if (showClient && !showAi) {
      out = out.filter((r) => String(r.Source).includes('Client'));
    } else if (showAi && !showClient) {
      out = out.filter((r) => String(r.Source).includes('AI'));
    } else if (!showClient && !showAi) {
      out = [];
    }
    return out.map((r, i) => ({ ...r, 'S.No': i + 1 }));
  }, [rules, selectedDims, showClient, showAi]);

  const allDims = useMemo(() => [...new Set(rules.map((r) => r.Dimension))], [rules]);

  const dimChart = useMemo(() => {
    if (filtered.length === 0) return null;
    const counts = {};
    filtered.forEach((r) => { counts[r.Dimension] = (counts[r.Dimension] || 0) + 1; });
    const labels = Object.keys(counts);
    const values = labels.map((l) => counts[l]);
    return {
      data: [{
        type: 'bar', x: labels, y: values,
        marker: { color: labels.map((l) => DIMENSION_BG[l] || '#94a3b8') },
      }],
      layout: { title: 'Rules by DQ Dimension' },
    };
  }, [filtered]);

  const sourceChart = useMemo(() => {
    if (filtered.length === 0) return null;
    let client = 0, ai = 0;
    filtered.forEach((r) => {
      if (String(r.Source).includes('Client')) client++;
      else ai++;
    });
    return {
      data: [{
        type: 'pie',
        labels: ['Client Rules', 'AI Rules'],
        values: [client, ai],
        marker: { colors: ['#86efac', '#93c5fd'] },
      }],
      layout: { title: 'Rules by Source' },
    };
  }, [filtered]);

  const total = rules.length;
  const clientCount = rules.filter((r) => String(r.Source).includes('Client')).length;
  const aiCount = rules.filter((r) => String(r.Source).includes('AI')).length;

  if (llm && !llm.configured) {
    return (
      <Alert severity="error">
        Azure OpenAI not configured. Missing: {(llm.missing || []).join(', ')}
        <br />Set these in <code>.streamlit/secrets.toml</code> or environment variables.
      </Alert>
    );
  }

  return (
    <Box>
      <Box sx={{ mb: 2 }}>
        <Typography variant="h6">Complete Data Quality Analysis</Typography>
        <Typography variant="body2" color="text.secondary">
          Click the button below to perform 100% complete analysis:
          <br />- Extract client rules from Excel metadata
          <br />- Generate AI-powered rules for all columns
          <br />- Display everything in a single unified table
        </Typography>
      </Box>

      <Stack direction="row" spacing={2} mb={2}>
        {!generated ? (
          <Button variant="contained" onClick={generate} disabled={busy}>
            {busy ? 'Performing 100% complete analysis…' : 'Generate Complete Analysis'}
          </Button>
        ) : (
          <Button variant="outlined" color="error" onClick={clear} disabled={busy}>
            Clear All Rules
          </Button>
        )}
      </Stack>
      {busy && <LinearProgress sx={{ mb: 2 }} />}
      {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}

      {generated && total > 0 && (
        <>
          <Box sx={{ bgcolor: '#f0f9ff', borderLeft: '4px solid #3b82f6', p: 1.75, mb: 2 }}>
            <Typography variant="body2">
              <b>Analysis Summary:</b> Total Rules: {total} | Client Rules: {clientCount} | AI Rules: {aiCount}
            </Typography>
          </Box>

          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="center" mb={2}>
            <FormControl size="small" sx={{ minWidth: 320, flex: 2 }}>
              <InputLabel>Filter by DQ Dimension</InputLabel>
              <Select multiple value={selectedDims}
                onChange={(e) => setSelectedDims(typeof e.target.value === 'string'
                  ? e.target.value.split(',') : e.target.value)}
                input={<OutlinedInput label="Filter by DQ Dimension" />}
                renderValue={(s) => s.join(', ')}>
                {allDims.map((d) => (
                  <MenuItem key={d} value={d}>{d}</MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControlLabel
              control={<Checkbox checked={showClient} onChange={(e) => setShowClient(e.target.checked)} />}
              label="Show Client Rules" />
            <FormControlLabel
              control={<Checkbox checked={showAi} onChange={(e) => setShowAi(e.target.checked)} />}
              label="Show AI Rules" />
          </Stack>

          <Typography variant="caption" color="text.secondary">Showing {filtered.length} rules</Typography>
          <TableContainer component={Paper} sx={{ mt: 1, maxHeight: 800 }}>
            <Table stickyHeader size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 600 }}>S.No</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Business Field</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Dimension</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Data Quality Rule</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Issues Found</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Issues Found Example</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filtered.map((r) => {
                  const issuesFound = Number(r['Issues Found']) || 0;
                  const issueExample = String(r['Issues Found Example'] || '');
                  let exampleStyle = {};
                  if (issueExample.startsWith('Client provided')) {
                    exampleStyle = { bgcolor: '#dcfce7', color: '#166534', fontWeight: 600 };
                  } else if (issueExample.startsWith('All values valid')) {
                    exampleStyle = { bgcolor: '#dcfce7', color: '#166534', fontStyle: 'italic' };
                  } else if (issueExample) {
                    exampleStyle = { bgcolor: '#fef3c7', color: '#92400e' };
                  }
                  return (
                    <TableRow key={r['S.No']}>
                      <TableCell>{r['S.No']}</TableCell>
                      <TableCell>{r['Business Field']}</TableCell>
                      <TableCell sx={{
                        bgcolor: DIMENSION_BG[r.Dimension] || 'transparent',
                        color: DIMENSION_FG[r.Dimension] || 'inherit',
                        fontWeight: 600,
                      }}>
                        {r.Dimension}
                      </TableCell>
                      <TableCell sx={{ fontSize: '0.8rem' }}>{r['Data Quality Rule']}</TableCell>
                      <TableCell sx={issuesFound > 0
                        ? { bgcolor: '#fee2e2', color: '#991b1b', fontWeight: 700 }
                        : { bgcolor: '#dcfce7', color: '#166534', fontWeight: 700 }}>
                        {issuesFound}
                      </TableCell>
                      <TableCell sx={{ fontSize: '0.78rem', ...exampleStyle, maxWidth: 320, wordBreak: 'break-word' }}>
                        {issueExample}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>

          <Grid container spacing={2} mt={2}>
            <Grid item xs={12} md={6}>{dimChart && <PlotlyChart {...dimChart} height={400} />}</Grid>
            <Grid item xs={12} md={6}>{sourceChart && <PlotlyChart {...sourceChart} height={400} />}</Grid>
          </Grid>
        </>
      )}
    </Box>
  );
}
