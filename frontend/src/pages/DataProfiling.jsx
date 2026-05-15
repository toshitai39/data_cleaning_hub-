import { useEffect, useState } from 'react';
import {
  Box, Tabs, Tab, Button, LinearProgress, Alert, Stack,
} from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import api from '../api.js';
import PageHeader from '../components/PageHeader.jsx';
import EmptyState from '../components/EmptyState.jsx';
import { useDataset } from '../context/DatasetContext.jsx';
import KpiBar from './profiling/KpiBar.jsx';
import ExecutiveSummaryTab from './profiling/ExecutiveSummaryTab.jsx';
import ExportTab from './profiling/ExportTab.jsx';

export default function DataProfiling() {
  const { state, refresh } = useDataset();
  const [tab, setTab] = useState(0);
  const [kpi, setKpi] = useState(null);
  const [executiveSummary, setExecutiveSummary] = useState(null);
  const [profiled, setProfiled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  // Data Profiling is the LIVE view — reflects the current working
  // dataset (sess.df), which is mutated by Cleansing + Find Duplicates.
  // Pass source=current so the numbers refresh after every cleansing
  // action, and so the top scorecard always agrees with the detailed
  // drill-down tabs (both read the same dataframe through the same
  // scoring code). The Initial Dashboard is the baseline-only view;
  // the Final Dashboard is the same data as here but with an
  // executive framing.
  const SRC = { params: { source: 'current' } };
  const load = () =>
    Promise.all([
      api.get('/profile/kpi', SRC),
      api.get('/profile/executive-summary', SRC).catch(() => ({ data: null })),
    ]).then(([kpiR, esR]) => {
      setKpi(kpiR.data);
      setExecutiveSummary(esR?.data || null);
      setProfiled(true);
    }).catch(() => setProfiled(false));

  useEffect(() => {
    if (state.loaded) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.loaded, state.operations]);

  const runProfile = async () => {
    setBusy(true); setErr('');
    try {
      await api.post('/profile/run');
      await load();
      await refresh();
    } catch (e) { setErr(e?.response?.data?.detail || 'Profiling failed'); }
    finally { setBusy(false); }
  };

  if (!state.loaded) {
    return (
      <>
        <PageHeader title="Data Profiling" subtitle="Per critical-data-element quality and risk analysis" />
        <EmptyState />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Data Profiling"
        subtitle="Data quality assessment across six dimensions — completeness, validation, uniqueness, standardisation, accuracy, timeliness."
        actions={
          <Button variant="contained" startIcon={<PlayArrowIcon />} onClick={runProfile} disabled={busy}>
            {busy ? 'Profiling…' : profiled ? 'Re-run Profile' : 'Run Profile'}
          </Button>
        }
      />
      {busy && <LinearProgress sx={{ mb: 2 }} />}
      {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}

      {!profiled && !busy && (
        <Alert severity="info">
          Click <b>Run Profile</b> to compute critical data element statistics, then explore the tabs below.
        </Alert>
      )}

      {profiled && (
        <>
          <KpiBar kpi={kpi} executiveSummary={executiveSummary} />
          <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
            <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" scrollButtons="auto">
              <Tab label="Executive Summary" />
              <Tab label="Export" />
            </Tabs>
          </Box>
          <Box sx={{ pt: 2 }}>
            {tab === 0 && <ExecutiveSummaryTab />}
            {tab === 1 && <ExportTab />}
          </Box>
        </>
      )}
    </>
  );
}
