import React, { createContext, useContext, useState, useEffect } from "react";
import { authApi } from "../services/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("cs_token");
    if (token) {
      authApi
        .me()
        .then((res) => setUser(res.data))
        .catch(() => localStorage.removeItem("cs_token"))
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const login = async (email, password) => {
    const res = await authApi.login({ email, password });
    localStorage.setItem("cs_token", res.data.access_token);
    setUser(res.data.user);
    return res.data.user;
  };

  // payload may now include `role` (Role-Based Authentication, Feature 6).
  // Backend defaults to "data_scientist" if role is omitted, so existing
  // callers that don't pass a role keep working unchanged.
  const register = async (payload) => {
    const res = await authApi.register(payload);
    localStorage.setItem("cs_token", res.data.access_token);
    setUser(res.data.user);
    return res.data.user;
  };

  const logout = () => {
    localStorage.removeItem("cs_token");
    setUser(null);
  };

  // Convenience helpers for role-gated UI (used by Layout.jsx nav and
  // various pages to show/hide admin-only or role-specific actions).
  const hasRole = (...roles) => !!user && (user.role === "admin" || roles.includes(user.role));

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, hasRole }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
