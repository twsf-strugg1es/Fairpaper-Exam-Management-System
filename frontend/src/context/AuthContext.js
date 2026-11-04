import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import api from '../api';

const AuthContext = createContext();

const SESSION_TIMEOUT = 5 * 60 * 1000; // idle sign-out after 5 minutes, unless "keep me signed in"
const TOKEN_REFRESH_MARGIN = 20 * 60 * 1000; // refresh when less than 20 minutes remain
// Set when Fairpaper signs someone out (idle, or the server no longer accepts the session), so the sign-in
// page can say their work is safe and bring them back to the same page
export const SIGNED_OUT_KEY = 'fp-signed-out';

// Membership roles that can manage questions, exams and grading / members and groups
const STAFF_ROLES = ['owner', 'admin', 'examiner'];
const MANAGER_ROLES = ['owner', 'admin'];

// Keep the preferred organization if the user still belongs to it; with exactly one, use that
const pickOrganization = (memberships, preferredId) => {
  if (!memberships?.length) return null;
  if (memberships.some((m) => m.organization_id === preferredId)) return preferredId;
  return memberships.length === 1 ? memberships[0].organization_id : null;
};

// Read the expiry (ms since epoch) from a JWT's payload; null if it can't be parsed
const getTokenExpiry = (jwt) => {
  try {
    const payload = JSON.parse(atob(jwt.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    return payload.exp ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [token, setToken] = useState(null);
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [rememberMe, setRememberMe] = useState(false);
  const [organizationId, setOrganizationId] = useState(null);

  // Check localStorage on initial load
  useEffect(() => {
    const storedToken = localStorage.getItem('token');
    const storedUser = localStorage.getItem('user');
    const storedRememberMe = localStorage.getItem('rememberMe') === 'true';
    const lastActivityTime = localStorage.getItem('lastActivityTime');
    
    // Check if session has expired (only if rememberMe is false)
    if (storedToken && storedUser && !storedRememberMe && lastActivityTime) {
      const now = Date.now();
      const lastActivity = parseInt(lastActivityTime);
      if (now - lastActivity > SESSION_TIMEOUT) {
        // Session expired
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        localStorage.removeItem('lastActivityTime');
        setIsLoading(false);
        return;
      }
    }
    
    if (storedToken && storedUser) {
      setToken(storedToken);
      setUser(JSON.parse(storedUser));
      setRememberMe(storedRememberMe);
      setOrganizationId(localStorage.getItem('organizationId'));
      // Update last activity time
      localStorage.setItem('lastActivityTime', Date.now().toString());
      // Memberships may have changed since the last visit (joined, removed, new role). Refreshed in the background:
      // waiting for it delayed every first screen by a round trip, which on a slow line is most of a second
      refreshUser();
      setIsLoading(false);
      return;
    }
    setIsLoading(false);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Set up session timeout check
  useEffect(() => {
    if (!token || rememberMe) return; // Skip if not logged in or if rememberMe is enabled
    
    const sessionTimeout = setInterval(() => {
      const lastActivityTime = localStorage.getItem('lastActivityTime');
      if (lastActivityTime) {
        const now = Date.now();
        const lastActivity = parseInt(lastActivityTime);
        if (now - lastActivity > SESSION_TIMEOUT) logout('idle');
      }
    }, 60000); // Check every minute
    
    return () => clearInterval(sessionTimeout);
  }, [token, rememberMe]);

  // A request the server refused for the session (401) ends it here too, with the same reassurance
  useEffect(() => {
    const onUnauthorized = () => { if (localStorage.getItem('token')) logout('expired'); };
    window.addEventListener('fp:unauthorized', onUnauthorized);
    return () => window.removeEventListener('fp:unauthorized', onUnauthorized);
  }); // eslint-disable-line react-hooks/exhaustive-deps -- re-bound each render, so it calls the current logout

  // Update activity time on user interaction
  useEffect(() => {
    if (!token) return;
    
    const updateActivityTime = () => {
      localStorage.setItem('lastActivityTime', Date.now().toString());
    };
    
    window.addEventListener('mousemove', updateActivityTime);
    window.addEventListener('keypress', updateActivityTime);
    window.addEventListener('click', updateActivityTime);
    
    return () => {
      window.removeEventListener('mousemove', updateActivityTime);
      window.removeEventListener('keypress', updateActivityTime);
      window.removeEventListener('click', updateActivityTime);
    };
  }, [token]);

  const selectOrganization = useCallback((id) => {
    setOrganizationId(id);
    if (id) {
      localStorage.setItem('organizationId', id);
    } else {
      localStorage.removeItem('organizationId');
    }
  }, []);

  const storeUser = useCallback((newUser) => {
    setUser(newUser);
    localStorage.setItem('user', JSON.stringify(newUser));
    selectOrganization(pickOrganization(newUser.memberships, localStorage.getItem('organizationId')));
  }, [selectOrganization]);

  const login = (newToken, newUser, saveLogin = false) => {
    setToken(newToken);
    setRememberMe(saveLogin);
    localStorage.setItem('token', newToken);
    localStorage.setItem('rememberMe', saveLogin.toString());
    localStorage.setItem('lastActivityTime', Date.now().toString());
    storeUser(newUser);
  };

  // A new token for the same person, e.g. after changing the password ends every other session
  const replaceToken = (newToken) => {
    setToken(newToken);
    localStorage.setItem('token', newToken);
  };

  // Reload the user and their memberships, e.g. after joining or creating an organization
  const refreshUser = useCallback(async () => {
    try {
      const response = await api.get('/me');
      storeUser(response.data);
      return response.data;
    } catch (err) {
      if (err.response?.status === 401) logout('expired');
      return null;
    }
  }, [storeUser]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keeps a long-running page (e.g. an exam) signed in: counts as activity for the
  // idle timeout and swaps the token for a fresh one before it expires.
  const refreshSession = useCallback(async () => {
    localStorage.setItem('lastActivityTime', Date.now().toString());
    const currentToken = localStorage.getItem('token');
    if (!currentToken) return;
    const expiresAt = getTokenExpiry(currentToken);
    if (expiresAt && expiresAt - Date.now() > TOKEN_REFRESH_MARGIN) return;
    try {
      const response = await api.post('/token/refresh');
      const newToken = response.data.access_token;
      setToken(newToken);
      localStorage.setItem('token', newToken);
    } catch (err) {
      console.error('Failed to refresh session:', err);
    }
  }, []);

  // reason: undefined when the person signs out themselves; 'idle' or 'expired' when Fairpaper does it
  const logout = (reason) => {
    if (typeof reason === 'string' && localStorage.getItem('token')) { // onClick={logout} passes an event: that's a normal sign-out
      try {
        sessionStorage.setItem(SIGNED_OUT_KEY, JSON.stringify({
          reason, path: `${window.location.pathname}${window.location.search}`, email: JSON.parse(localStorage.getItem('user') || '{}').email,
        }));
      } catch {
        // the sign-in page just won't have the details
      }
    }
    setToken(null);
    setUser(null);
    setRememberMe(false);
    setOrganizationId(null);
    localStorage.removeItem('organizationId');
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    localStorage.removeItem('rememberMe');
    localStorage.removeItem('lastActivityTime');
  };

  const currentMembership = user?.memberships?.find((m) => m.organization_id === organizationId) || null;

  const value = {
    token,
    user,
    login,
    logout,
    refreshSession,
    refreshUser,
    replaceToken,
    isLoading,
    rememberMe,
    // The organization the user is working in, and their role there
    currentMembership,
    selectOrganization,
    isStaff: STAFF_ROLES.includes(currentMembership?.role),
    isManager: MANAGER_ROLES.includes(currentMembership?.role),
    isCandidate: currentMembership?.role === 'candidate',
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
