import axios from 'axios';

const api = axios.create({
  baseURL: process.env.REACT_APP_API_URL || 'http://localhost:8000',
});

// Request interceptor to add token to Authorization header
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    // Organization-scoped endpoints act on the organization the user selected
    const organizationId = localStorage.getItem('organizationId');
    if (organizationId) {
      config.headers['X-Organization-Id'] = organizationId;
    }
    // Do NOT set a default Content-Type here; axios will set
    // the appropriate one automatically (e.g., multipart/form-data for FormData).
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const signedIn = Boolean(error.config?.headers?.Authorization);
    const signingIn = /\/token$/.test(error.config?.url || '');
    if (error.response?.status === 401 && signedIn && !signingIn) window.dispatchEvent(new Event('fp:unauthorized'));
    return Promise.reject(error);
  },
);

export default api;
