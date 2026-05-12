import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import api from '../api.js';
import { useAuth } from './AuthContext.jsx';
import { useProject } from './ProjectContext.jsx';

const DatasetContext = createContext(null);

export function DatasetProvider({ children }) {
  const { user } = useAuth();
  const { active } = useProject();
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

  // Re-fetch dataset state on mount, whenever the user changes (login /
  // logout), AND whenever the active project changes. The server binds
  // its in-memory ``sess.df`` to the working parquet on ``GET /projects/{id}``,
  // so the frontend needs to pull /data/state again to learn that data
  // has been loaded for the new project.
  useEffect(() => {
    refresh();
  }, [refresh, active?.id]);

  return (
    <DatasetContext.Provider value={{ state, refresh }}>
      {children}
    </DatasetContext.Provider>
  );
}

export function useDataset() {
  return useContext(DatasetContext);
}
