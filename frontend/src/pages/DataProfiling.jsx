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
import OverviewTab from './profiling/OverviewTab.jsx';
import DriftTab from './profiling/DriftTab.jsx';
import MatchRulesTab from './profiling/MatchRulesTab.jsx';
import ExportTab from './profiling/ExportTab.jsx';
import AiRulesTab from './profiling/AiRulesTab.jsx';

export default function DataProfiling() {
  const { state, refresh } = useDataset();
  const [tab, setTab] = useState(0);
  const [kpi, setKpi] = useState(null);
  const [profiled, setProfiled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const load = () =>
    api.get('/profile/kpi')
      .then((r) => { setKpi(r.data); setProfiled(true); })
      .catch(() => setProfiled(false));

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
        subtitle="Profile your dataset, generate AI rules, and detect drift."
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
          <KpiBar kpi={kpi} />
          <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
            <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" scrollButtons="auto">
              <Tab label="Overview" />
              <Tab label="Data Glossary" />
              <Tab label="Data Drift" />
              <Tab label="Match Rules" />
              <Tab label="Export" />
            </Tabs>
          </Box>
          <Box sx={{ pt: 2 }}>
            {tab === 0 && <OverviewTab />}
            {tab === 1 && <AiRulesTab />}
            {tab === 2 && <DriftTab />}
            {tab === 3 && <MatchRulesTab />}
            {tab === 4 && <ExportTab />}
          </Box>
        </>
      )}
    </>
  );
}
