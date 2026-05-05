import React from 'react';
import ReactDOM from 'react-dom/client';
import { ThemeProvider, CssBaseline } from '@mui/material';
import App from './App.jsx';
import { theme } from './theme.js';
import { AuthProvider } from './context/AuthContext.jsx';
import { DatasetProvider } from './context/DatasetContext.jsx';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AuthProvider>
        <DatasetProvider>
          <App />
        </DatasetProvider>
      </AuthProvider>
    </ThemeProvider>
  </React.StrictMode>
);
