import { createContext, useContext, useEffect, useState } from 'react';
import api, { clearSession, setSessionId } from '../api.js';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const raw = localStorage.getItem('dpp_user');
    return raw ? JSON.parse(raw) : null;
  });
  const [checking, setChecking] = useState(true);

  // Re-validate the persisted session against the server on app mount.
  // The server-side session store is in-memory: a backend restart wipes
  // every session, so the client may think it's logged in when the
  // server has no record. Calling /auth/me 401s in that case → drop
  // local state and force a fresh login.
  useEffect(() => {
    let cancelled = false;
    const verify = async () => {
      if (!user) {
        setChecking(false);
        return;
      }
      try {
        const { data } = await api.get('/auth/me');
        if (cancelled) return;
        // Keep local user in sync if the server has a different display name.
        const fresh = { username: data.username, name: data.name };
        localStorage.setItem('dpp_user', JSON.stringify(fresh));
        setUser(fresh);
      } catch (e) {
        if (cancelled) return;
        if (e?.response?.status === 401) {
          clearSession();
          setUser(null);
        }
      } finally {
        if (!cancelled) setChecking(false);
      }
    };
    verify();
    return () => { cancelled = true; };
    // We only want this on mount — not on every state change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = async (username, password) => {
    const { data } = await api.post('/auth/login', { username, password });
    setSessionId(data.session_id);
    const u = { username: data.username, name: data.name };
    localStorage.setItem('dpp_user', JSON.stringify(u));
    setUser(u);
    return u;
  };

  const register = async (username, password, name) => {
    const { data } = await api.post('/auth/register', { username, password, name });
    setSessionId(data.session_id);
    const u = { username: data.username, name: data.name };
    localStorage.setItem('dpp_user', JSON.stringify(u));
    setUser(u);
    return u;
  };

  const logout = () => {
    clearSession();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, login, register, logout, checking }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
