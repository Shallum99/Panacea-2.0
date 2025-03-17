import apiClient from './client';

// Enums for resume sections
export enum ResumeSection {
  SKILLS = 'SKILLS',
  PROJECTS = 'PROJECTS',
  EXPERIENCE = 'EXPERIENCE'
}

// Types for API requests and responses
export interface SectionContent {
  original: string;
  optimized: string;
}

export interface ResumeTailorRequest {
  jobDescription: string;
  resumeId: number;
  sectionsToOptimize: ResumeSection[];
}

export interface ResumeTailorResponse {
  originalATSScore: number;
  optimizedATSScore: number;
  optimizedSections: Record<ResumeSection, SectionContent>;
}

export interface ATSScoreRequest {
  jobDescription: string;
  resumeContent: string;
}

export interface ATSScoreResponse {
  score: number;
  breakdown: Record<string, number>;
  suggestions: string[];
}

/**
 * Optimize a resume based on a job description
 * @param jobDescription The job description to optimize against
 * @param resumeId The ID of the resume to optimize
 * @param sectionsToOptimize Array of resume sections to optimize
 * @returns Promise with optimization results
 */
export const optimizeResume = async (
  jobDescription: string,
  resumeId: number,
  sectionsToOptimize: ResumeSection[]
): Promise<ResumeTailorResponse> => {
  const response = await apiClient.post<ResumeTailorResponse>('/resume-tailor/optimize', {
    jobDescription,
    resumeId,
    sectionsToOptimize
  });
  
  return response.data;
};

/**
 * Calculate ATS score for a resume against a job description
 * @param jobDescription The job description to score against
 * @param resumeContent The resume content to score
 * @returns Promise with score results
 */
export const calculateATSScore = async (
  jobDescription: string,
  resumeContent: string
): Promise<ATSScoreResponse> => {
  const response = await apiClient.post<ATSScoreResponse>('/resume-tailor/score', {
    jobDescription,
    resumeContent
  });
  
  return response.data;
};