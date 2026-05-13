import { useEffect, useState } from 'react';
import { Box, Tabs, Tab, Alert, LinearProgress } from '@mui/material';
import api from '../api.js';
import PageHeader from '../components/PageHeader.jsx';
import EmptyState from '../components/EmptyState.jsx';
import { useDataset } from '../context/DatasetContext.jsx';
import ExactTab from './duplicates/ExactTab.jsx';
import FuzzyTab from './duplicates/FuzzyTab.jsx';
import CombinedTab from './duplicates/CombinedTab.jsx';
import LibraryRulesTab from './duplicates/LibraryRulesTab.jsx';

export default function FindDuplicates() {
  const { state } = useDataset();
  const [tab, setTab] = useState(0);
  const [columns, setColumns] = useState({ all: [], object_only: [] });
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!state.loaded) return;
    setLoading(true);
    api.get('/duplicates/columns')
      .then((r) => setColumns(r.data))
      .catch((e) => setErr(e?.response?.data?.detail || 'Failed to load critical data elements'))
      .finally(() => setLoading(false));
  }, [state.loaded, state.operations]);

  if (!state.loaded) {
    return (
      <>
        <PageHeader title="Find Duplicates" subtitle="Exact, Fuzzy and Combined matching" />
        <EmptyState />
      </>
    );
  }

  return (
    <>
      <PageHeader title="Find Duplicates" />
      {loading && <LinearProgress sx={{ mb: 2 }} />}
      {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}

      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)}>
          <Tab label="Library rules" />
          <Tab label="Exact Match" />
          <Tab label="Fuzzy Match" />
          <Tab label="Combined Match" />
        </Tabs>
      </Box>

      {tab === 0 && <LibraryRulesTab />}
      {tab === 1 && <ExactTab allColumns={columns.all} />}
      {tab === 2 && <FuzzyTab objectColumns={columns.object_only} />}
      {tab === 3 && <CombinedTab allColumns={columns.all} objectColumns={columns.object_only} />}
    </>
  );
}
