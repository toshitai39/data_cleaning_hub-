import { createContext, useContext, useEffect, useState } from 'react';
import api, { clearSession, setSessionId } from '../api.js';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const raw = localStorage.getItem('dpp_user');
    return raw ? JSON.parse(raw) : null;
  });

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
    <AuthContext.Provider value={{ user, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
