import apiClient from './client';

// Types
export interface Resume {
  id: number;
  title: string;
  filename: string;
  is_active: boolean;
  extracted_info: {
    name: string;
    email: string;
    phone: string;
    skills: string[];
    years_experience: string;
    education: string;
    recent_job: string;
    recent_company: string;
  };
  profile_classification: {
    profile_type: string;
    primary_languages: string[];
    frameworks: string[];
    years_experience: string;
    seniority: string;
    industry_focus: string;
  };
}

// Upload a resume
export const uploadResume = async (file: File, title: string, makeActive: boolean = true) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('title', title);
  formData.append('make_active', String(makeActive));
  
  const response = await apiClient.post<Resume>('/resumes/', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  
  return response.data;
};

// Get all resumes
export const getResumes = async () => {
  const response = await apiClient.get<Resume[]>('/resumes/');
  return response.data;
};

// Get active resume
export const getActiveResume = async () => {
  const response = await apiClient.get<Resume>('/resumes/active');
  return response.data;
};

// Set a resume as active
export const setActiveResume = async (resumeId: number) => {
  const response = await apiClient.post<Resume>(`/resumes/${resumeId}/set-active`);
  return response.data;
};

// Get resume by ID
export const getResume = async (resumeId: number) => {
  const response = await apiClient.get<Resume>(`/resumes/${resumeId}`);
  return response.data;
};

// Get resume content by ID
export const getResumeContent = async (resumeId: number) => {
  const response = await apiClient.get<Resume & { content: string }>(`/resumes/${resumeId}/content`);
  return response.data;
};