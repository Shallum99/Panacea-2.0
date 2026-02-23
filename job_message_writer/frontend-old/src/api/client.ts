import axios from 'axios';

// Create an axios instance with default configuration
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api', // Use environment variable with fallback
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add request interceptor to include credentials and authentication token
apiClient.interceptors.request.use(
  (config) => {
    // Include credentials
    config.withCredentials = true;
    
    // Get token from local storage
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    
    console.log('API Request:', {
      url: config.url,
      method: config.method,
      data: config.data
    });
    
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

apiClient.interceptors.response.use(
  (response) => {
    console.log('API Response:', response.data);
    return response;
  },
  (error) => {
    console.error('API Error:', {
      message: error.message,
      response: error.response?.data
    });
    
    // Handle authorization errors
    if (error.response && error.response.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    
    return Promise.reject(error);
  }
);

export default apiClient;