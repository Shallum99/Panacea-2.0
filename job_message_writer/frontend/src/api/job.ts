import apiClient from './client';

// Types
export interface CompanyInfo {
  company_name: string;
  industry: string;
  company_size: string;
  company_culture: string[];
  technologies: string[];
  location: string;
  mission: string;
}

export interface JobDescription {
  id: number;
  title: string;
  content: string;
  company_info: CompanyInfo;
}

// Analyze job description
export const analyzeJobDescription = async (content: string) => {
  const response = await apiClient.post<CompanyInfo>('/job-descriptions/analyze', {
    content,
  });
  
  return response.data;
};

// Create job description
export const createJobDescription = async (content: string, title?: string) => {
  const response = await apiClient.post<JobDescription>('/job-descriptions/', {
    content,
    title,
  });
  
  return response.data;
};

// Get all job descriptions
export const getJobDescriptions = async (skip: number = 0, limit: number = 100) => {
  const response = await apiClient.get<JobDescription[]>('/job-descriptions/', {
    params: { skip, limit },
  });
  
  return response.data;
};

// Get job description by ID
export const getJobDescription = async (jobId: number) => {
  const response = await apiClient.get<JobDescription>(`/job-descriptions/${jobId}`);
  return response.data;
};