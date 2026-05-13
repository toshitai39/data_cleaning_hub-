import { useState } from 'react';
import {
  Box, Grid, Paper, Typography, Button, Stack, Alert, LinearProgress, Checkbox,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Tabs, Tab, Accordion, AccordionSummary, AccordionDetails, Divider, Chip,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import api from '../../api.js';
import GroupDetail from './GroupDetail.jsx';

function MetricCard({ label, value }) {
  return (
    <Paper sx={{ p: 2, textAlign: 'center' }}>
      <Typography variant="caption" color="text.secondary"
        sx={{ textTransform: 'uppercase', letterSpacing: 0.6 }}>{label}</Typography>
      <Typography variant="h6" sx={{ fontWeight: 700, color: 'primary.main' }}>{value}</Typography>
    </Paper>
  );
}

export default function DuplicateResults({
  dupType, summaries, totalGroups, totalRows,
  onRemoveAll, removeAllControls, onScanAgain,
}) {
  const [picked, setPicked] = useState({});
  const [activeTab, setActiveTab] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const togglePick = (gid) => setPicked((p) => ({ ...p, [gid]: !p[gid] }));

  const selectedIds = Object.entries(picked).filter(([_, v]) => v).map(([k]) => parseInt(k, 10));

  const downloadBlob = async (path, body, defaultName) => {
    setBusy(true); setErr('');
    try {
      const res = await api.post(path, body, { responseType: 'blob' });
      const cd = res.headers['content-disposition'] || '';
      const m = cd.match(/filename="?([^"]+)"?/);
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([res.data]));
      a.download = m ? m[1] : defaultName; a.click();
    } catch (e) { setErr('Download failed'); }
    finally { setBusy(false); }
  };

  const exportAll = () => downloadBlob(`/duplicates/${dupType}/export`, null, `${dupType}.xlsx`);
  const exportSelected = () => downloadBlob(`/duplicates/${dupType}/export-selected`,
    { group_ids: selectedIds }, `${dupType}_selected.xlsx`);

  const bulk = async (strategy) => {
    if (selectedIds.length === 0) return;
    setBusy(true); setErr('');
    try {
      await api.post(`/duplicates/${dupType}/bulk`, { group_ids: selectedIds, strategy });
      setPicked({});
      onScanAgain?.();
    } catch (e) { setErr(e?.response?.data?.detail || 'Failed'); }
    finally { setBusy(false); }
  };

  if (totalGroups === 0) return null;

  // First 10 in tabs, rest in expanders (matches Streamlit behaviour)
  const inTabs = summaries.slice(0, totalGroups <= 10 ? 10 : 5);
  const inMore = totalGroups <= 10 ? [] : summaries.slice(5, 20);

  return (
    <Box>
      {err && <Alert severity="error" sx={{ mb: 1 }}>{err}</Alert>}
      {busy && <LinearProgress sx={{ mb: 1 }} />}

      {/* Top metrics + Remove All + Export All */}
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}>
          <MetricCard label="Duplicate Groups" value={totalGroups} />
        </Grid>
        <Grid item xs={6} md={3}>
          <MetricCard label="Total Duplicate Rows" value={totalRows} />
        </Grid>
        <Grid item xs={12} md={3}>
          {removeAllControls}
        </Grid>
        <Grid item xs={12} md={3}>
          <Button fullWidth variant="outlined" sx={{ height: '100%' }} onClick={exportAll}>
            Export All to Excel
          </Button>
        </Grid>
      </Grid>

      <Divider sx={{ my: 2 }} />

      {/* Summary table */}
      <Typography variant="h6" gutterBottom>Duplicate Groups Summary</Typography>
      <TableContainer component={Paper} variant="outlined" sx={{ mb: 2, maxHeight: 360 }}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 600, width: 60 }}>Select</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>Group ID</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>Rows</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>Similarity</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>Match Type</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>Key critical data elements</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>Preview</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {summaries.map((s) => (
              <TableRow key={s.group_id} hover>
                <TableCell><Checkbox size="small" checked={!!picked[s.group_id]}
                  onChange={() => togglePick(s.group_id)} /></TableCell>
                <TableCell>Group #{s.group_id}</TableCell>
                <TableCell>{s.rows}</TableCell>
                <TableCell>{s.similarity.toFixed(1)}%</TableCell>
                <TableCell><Chip size="small" label={s.match_type} variant="outlined" /></TableCell>
                <TableCell>
                  <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>
                    {(s.key_columns || []).length === 0 ? 'All' : s.key_columns.join(', ')}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="caption" sx={{ fontFamily: 'monospace', fontSize: '0.72rem' }}>
                    {s.representative}
                  </Typography>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Bulk actions for selected */}
      {selectedIds.length > 0 && (
        <>
          <Alert severity="info" sx={{ mb: 1 }}>{selectedIds.length} group(s) selected</Alert>
          <Grid container spacing={1.5} sx={{ mb: 2 }}>
            <Grid item xs={12} sm={3}>
              <Button fullWidth variant="outlined" onClick={() => bulk('keep_first')}>
                Keep First (Selected)
              </Button>
            </Grid>
            <Grid item xs={12} sm={3}>
              <Button fullWidth variant="outlined" onClick={() => bulk('keep_last')}>
                Keep Last (Selected)
              </Button>
            </Grid>
            <Grid item xs={12} sm={3}>
              <Button fullWidth variant="outlined" onClick={() => bulk('merge')}>
                Merge (Selected)
              </Button>
            </Grid>
            <Grid item xs={12} sm={3}>
              <Button fullWidth variant="outlined" onClick={exportSelected}>
                Export Selected
              </Button>
            </Grid>
          </Grid>
        </>
      )}

      <Divider sx={{ my: 2 }} />

      <Typography variant="h6" gutterBottom>Detailed View by Group</Typography>

      {/* Tabs for first 10 (or 5 if total > 10) */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
        <Tabs value={activeTab} onChange={(_, v) => setActiveTab(v)} variant="scrollable" scrollButtons="auto">
          {inTabs.map((s) => <Tab key={s.group_id} label={`Group #${s.group_id}`} />)}
          {inMore.length > 0 && <Tab label="More Groups…" />}
        </Tabs>
      </Box>
      <Box sx={{ pt: 2 }}>
        {activeTab < inTabs.length && (
          <GroupDetail dupType={dupType}
            groupId={inTabs[activeTab].group_id}
            onChanged={onScanAgain} />
        )}
        {activeTab === inTabs.length && inMore.length > 0 && (
          <Box>
            <Typography variant="subtitle2" gutterBottom>Additional Groups:</Typography>
            {inMore.map((s) => (
              <Accordion key={s.group_id} disableGutters elevation={0}
                sx={{ border: '1px solid', borderColor: 'divider', '&:before': { display: 'none' }, mb: 1 }}>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography>Group #{s.group_id} — {s.rows} rows — {s.similarity.toFixed(1)}% similarity</Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <GroupDetail dupType={dupType} groupId={s.group_id} onChanged={onScanAgain} />
                </AccordionDetails>
              </Accordion>
            ))}
          </Box>
        )}
      </Box>
    </Box>
  );
}
