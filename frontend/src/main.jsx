import React from 'react';
import ReactDOM from 'react-dom/client';
import { ThemeProvider, CssBaseline } from '@mui/material';
import App from './App.jsx';
import { theme } from './theme.js';
import { AuthProvider } from './context/AuthContext.jsx';
import { DatasetProvider } from './context/DatasetContext.jsx';
import { ProjectProvider } from './context/ProjectContext.jsx';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AuthProvider>
        <ProjectProvider>
          <DatasetProvider>
            <App />
          </DatasetProvider>
        </ProjectProvider>
      </AuthProvider>
    </ThemeProvider>
  </React.StrictMode>
);
