import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import api from '../api.js';
import { useAuth } from './AuthContext.jsx';

const ProjectContext = createContext({
  active: null,
  setActive: () => {},
  projects: [],
  refresh: async () => {},
  loading: false,
});

export function ProjectProvider({ children }) {
  const { user } = useAuth();
  const [active, setActiveState] = useState(null);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!user) {
      setProjects([]);
      setActiveState(null);
      return;
    }
    setLoading(true);
    try {
      const [{ data: list }, { data: dash }] = await Promise.all([
        api.get('/projects'),
        api.get('/projects/dashboard'),
      ]);
      setProjects(list || []);
      if (dash?.active_project_id) {
        const found = (list || []).find((p) => p.id === dash.active_project_id) || null;
        setActiveState(found);
      } else {
        setActiveState(null);
      }
    } catch (_) {
      // user may not be logged in yet
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => { refresh(); }, [refresh]);

  const setActive = useCallback(async (project) => {
    if (!project) {
      setActiveState(null);
      return;
    }
    try {
      const { data } = await api.get(`/projects/${project.id}`);
      setActiveState(data);
      // Update the list so last_opened_at reorders correctly next refresh.
      refresh();
    } catch (_) {
      setActiveState(project);
    }
  }, [refresh]);

  const value = useMemo(
    () => ({ active, setActive, projects, refresh, loading }),
    [active, setActive, projects, refresh, loading],
  );
  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useProject() {
  return useContext(ProjectContext);
}
