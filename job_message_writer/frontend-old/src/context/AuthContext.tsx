import React, { createContext, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { login as apiLogin, signup as apiSignup, logout as apiLogout, isAuthenticated, getCurrentUser, fetchCurrentUser } from '../api/auth';

// Types
type User = {
  id: number;
  email: string;
};

type AuthContextType = {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  logout: () => void;
};

// Create context
export const AuthContext = createContext<AuthContextType>({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  login: async () => {},
  signup: async () => {},
  logout: () => {},
});

// Provider component
export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const navigate = useNavigate();

  // Check if user is already logged in
  useEffect(() => {
    const checkAuth = async () => {
      try {
        if (isAuthenticated()) {
          const currentUser = getCurrentUser();
          if (currentUser) {
            // Optional: Validate token with backend
            try {
              const validatedUser = await fetchCurrentUser();
              setUser(validatedUser);
            } catch (error) {
              // Token might be invalid, clear local storage
              apiLogout();
              setUser(null);
            }
          }
        }
      } catch (error) {
        console.error('Authentication check failed:', error);
        apiLogout();
        setUser(null);
      } finally {
        setIsLoading(false);
      }
    };

    checkAuth();
  }, []);

  // Login function
  const login = async (email: string, password: string) => {
    try {
      setIsLoading(true);
      const response = await apiLogin({ email, password });
      
      setUser({
        id: response.user_id,
        email: response.email
      });
      
      // Check if user has uploaded a resume
      // This would be a separate API call in a real app
      const hasResume = false; // In real app, check with API
      
      // Redirect based on resume status
      if (hasResume) {
        navigate('/dashboard');
      } else {
        navigate('/resume-upload');
      }
    } catch (error) {
      console.error('Login failed:', error);
      throw error;
    } finally {
      setIsLoading(false);
    }
  };

  // Signup function
  const signup = async (email: string, password: string) => {
    try {
      setIsLoading(true);
      const response = await apiSignup({ email, password });
      
      setUser({
        id: response.user_id,
        email: response.email
      });
      
      // Always redirect to resume upload after signup
      navigate('/resume-upload');
    } catch (error) {
      console.error('Signup failed:', error);
      throw error;
    } finally {
      setIsLoading(false);
    }
  };

  // Logout function
  const logout = () => {
    apiLogout();
    setUser(null);
    navigate('/login');
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        signup,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};