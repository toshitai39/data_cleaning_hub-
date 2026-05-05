import { useState } from 'react';
import { Box } from '@mui/material';
import { useAuth } from './context/AuthContext.jsx';
import LoginPage from './pages/LoginPage.jsx';
import Sidebar from './components/Sidebar.jsx';
import TopTabs from './components/TopTabs.jsx';
import ErrorBoundary from './components/ErrorBoundary.jsx';
import Dashboard from './pages/Dashboard.jsx';
import LoadData from './pages/LoadData.jsx';
import RuleGenerator from './pages/RuleGenerator.jsx';
import DataProfiling from './pages/DataProfiling.jsx';
import FindDuplicates from './pages/FindDuplicates.jsx';
import DataQuality from './pages/DataQuality.jsx';
import Compare from './pages/Compare.jsx';
import MultiFile from './pages/MultiFile.jsx';
import Preview from './pages/Preview.jsx';
import Export from './pages/Export.jsx';

const TABS = [
  { label: 'Dashboard', component: <Dashboard /> },
  { label: 'Load Data', component: <LoadData /> },
  { label: 'Rule Generator', component: <RuleGenerator /> },
  { label: 'Data Profiling', component: <DataProfiling /> },
  { label: 'Find Duplicates', component: <FindDuplicates /> },
  { label: 'Data Quality', component: <DataQuality /> },
  { label: 'Compare', component: <Compare /> },
  { label: 'Multi-File', component: <MultiFile /> },
  { label: 'Preview', component: <Preview /> },
  { label: 'Export', component: <Export /> },
];

export default function App() {
  const { user } = useAuth();
  const [tab, setTab] = useState(0);

  if (!user) {
    return <LoginPage />;
  }

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: 'background.default' }}>
      <Sidebar />
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <TopTabs tabs={TABS.map((t) => t.label)} value={tab} onChange={setTab} />
        <Box sx={{ flex: 1, p: { xs: 2, md: 3 }, overflow: 'auto' }}>
          <ErrorBoundary key={tab}>{TABS[tab].component}</ErrorBoundary>
        </Box>
      </Box>
    </Box>
  );
}
