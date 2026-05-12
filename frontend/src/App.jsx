import { useState } from 'react';
import { Box } from '@mui/material';
import { useAuth } from './context/AuthContext.jsx';
import LoginPage from './pages/LoginPage.jsx';
import Sidebar from './components/Sidebar.jsx';
import TopBar from './components/TopBar.jsx';
import ErrorBoundary from './components/ErrorBoundary.jsx';
import Home from './pages/Home.jsx';
import NewAnalysis from './pages/NewAnalysis.jsx';
import LoadData from './pages/LoadData.jsx';
import Dashboard from './pages/Dashboard.jsx';
import RuleGenerator from './pages/RuleGenerator.jsx';
import DataProfiling from './pages/DataProfiling.jsx';
import FindDuplicates from './pages/FindDuplicates.jsx';
import DataQuality from './pages/DataQuality.jsx';
import Compare from './pages/Compare.jsx';
import Preview from './pages/Preview.jsx';
import Export from './pages/Export.jsx';

export default function App() {
  const { user } = useAuth();
  const [active, setActive] = useState('home');

  if (!user) {
    return <LoginPage />;
  }

  const routes = {
    home: <Home onNavigate={setActive} />,
    new: <NewAnalysis onCancel={() => setActive('home')} onCreated={() => setActive('load')} />,
    load: <LoadData />,
    dashboard: <Dashboard />,
    profile: <DataProfiling />,
    rules: <RuleGenerator />,
    quality: <DataQuality />,
    dupes: <FindDuplicates />,
    compare: <Compare />,
    preview: <Preview />,
    export: <Export />,
  };

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: '#F7F5FA' }}>
      <Sidebar activeKey={active} onSelect={setActive} />
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <TopBar activeKey={active} />
        <Box sx={{ flex: 1, px: { xs: 2, md: 4 }, py: { xs: 2, md: 3 }, overflow: 'auto' }}>
          <ErrorBoundary key={active}>{routes[active]}</ErrorBoundary>
        </Box>
      </Box>
    </Box>
  );
}
