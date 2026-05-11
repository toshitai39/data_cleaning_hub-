import { useState } from 'react';
import { Box } from '@mui/material';
import { useAuth } from './context/AuthContext.jsx';
import LoginPage from './pages/LoginPage.jsx';
import Sidebar from './components/Sidebar.jsx';
import ErrorBoundary from './components/ErrorBoundary.jsx';
import LoadData from './pages/LoadData.jsx';
import RuleGenerator from './pages/RuleGenerator.jsx';
import DataProfiling from './pages/DataProfiling.jsx';
import FindDuplicates from './pages/FindDuplicates.jsx';
import DataQuality from './pages/DataQuality.jsx';
import Compare from './pages/Compare.jsx';
import Preview from './pages/Preview.jsx';
import Export from './pages/Export.jsx';

const ROUTES = {
  load: <LoadData />,
  profile: <DataProfiling />,
  rules: <RuleGenerator />,
  quality: <DataQuality />,
  dupes: <FindDuplicates />,
  compare: <Compare />,
  preview: <Preview />,
  export: <Export />,
};

export default function App() {
  const { user } = useAuth();
  const [active, setActive] = useState('load');

  if (!user) {
    return <LoginPage />;
  }

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: 'background.default' }}>
      <Sidebar activeKey={active} onSelect={setActive} />
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <Box sx={{ flex: 1, p: { xs: 2, md: 3 }, overflow: 'auto' }}>
          <ErrorBoundary key={active}>{ROUTES[active]}</ErrorBoundary>
        </Box>
      </Box>
    </Box>
  );
}
