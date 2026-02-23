import apiClient from './client';

// Types
export interface User {
  id: number;
  email: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user_id: number;
  email: string;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface SignupCredentials {
  email: string;
  password: string;
}

// Login user
export const login = async (credentials: LoginCredentials): Promise<AuthResponse> => {
  try {
    console.log('Login credentials:', credentials); // For debugging
    const response = await apiClient.post<AuthResponse>('/auth/login', credentials);
    
    // Save user data and token to local storage
    localStorage.setItem('token', response.data.access_token);
    localStorage.setItem('user', JSON.stringify({
      id: response.data.user_id,
      email: response.data.email
    }));
    
    return response.data;
  } catch (error) {
    console.error('Login error:', error);
    throw error;
  }
};

// Sign up new user
export const signup = async (credentials: SignupCredentials): Promise<AuthResponse> => {
  try {
    const response = await apiClient.post<AuthResponse>('/auth/signup', credentials);
    
    // Save user data and token to local storage
    localStorage.setItem('token', response.data.access_token);
    localStorage.setItem('user', JSON.stringify({
      id: response.data.user_id,
      email: response.data.email
    }));
    
    return response.data;
  } catch (error) {
    console.error('Signup error:', error);
    throw error;
  }
};

// Logout user
export const logout = (): void => {
  localStorage.removeItem('token');
  localStorage.removeItem('user');
};

// Check if user is authenticated
export const isAuthenticated = (): boolean => {
  const user = localStorage.getItem('user');
  const token = localStorage.getItem('token');
  
  return !!user && !!token;
};

// Get current user data
export const getCurrentUser = (): User | null => {
  const userStr = localStorage.getItem('user');
  if (userStr) {
    try {
      return JSON.parse(userStr);
    } catch (error) {
      console.error('Error parsing user data:', error);
      return null;
    }
  }
  return null;
};

// Get current user data from API
export const fetchCurrentUser = async (): Promise<User> => {
  try {
    const response = await apiClient.get<User>('/auth/me');
    return response.data;
  } catch (error) {
    console.error('Error fetching current user:', error);
    throw error;
  }
};