import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import api from '../api.js';
import { useAuth } from './AuthContext.jsx';

const DatasetContext = createContext(null);

export function DatasetProvider({ children }) {
  const { user } = useAuth();
  const [state, setState] = useState({
    loaded: false,
    filename: null,
    rows: 0,
    columns: 0,
    quality_score: null,
    operations: 0,
  });

  const refresh = useCallback(async () => {
    if (!user) return;
    try {
      const { data } = await api.get('/data/state');
      setState(data);
    } catch (err) {
      // ignore — server may be down or session expired
    }
  }, [user]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <DatasetContext.Provider value={{ state, refresh }}>
      {children}
    </DatasetContext.Provider>
  );
}

export function useDataset() {
  return useContext(DatasetContext);
}
