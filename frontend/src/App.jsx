import { useState } from 'react';
import { Box } from '@mui/material';
import { useAuth } from './context/AuthContext.jsx';
import { useProject } from './context/ProjectContext.jsx';
import api from './api.js';
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
  const { active: activeProject, setActive: setActiveProject } = useProject();
  const [active, setActive] = useState('home');

  if (!user) {
    return <LoginPage />;
  }

  // Wrap tab navigation so going back to Home or New Analysis "closes"
  // the current project: clears the active-project state and detaches
  // the server session. The sidebar lock + breadcrumb chip both react
  // to this state, so the rest of the UI feels like a real workflow
  // step instead of a passive view.
  const navigate = (key) => {
    if ((key === 'home' || key === 'new') && activeProject) {
      const closingId = activeProject.id;
      setActiveProject(null);
      api.post(`/projects/${closingId}/close`).catch(() => { /* best-effort */ });
    }
    setActive(key);
  };

  const routes = {
    home: <Home onNavigate={navigate} />,
    new: <NewAnalysis onCancel={() => navigate('home')} onCreated={() => setActive('load')} />,
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
      <Sidebar activeKey={active} onSelect={navigate} />
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <TopBar activeKey={active} />
        <Box sx={{ flex: 1, px: { xs: 2, md: 4 }, py: { xs: 2, md: 3 }, overflow: 'auto' }}>
          <ErrorBoundary key={active}>{routes[active]}</ErrorBoundary>
        </Box>
      </Box>
    </Box>
  );
}
