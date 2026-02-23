import apiClient from './client';
import { CompanyInfo } from './job';

// Types
export interface ProfileClassification {
  profile_type: string;
  primary_languages: string[];
  frameworks: string[];
  years_experience: string;
  seniority: string;
  industry_focus: string;
}

export interface MessageResponse {
  message: string;
  company_info: CompanyInfo;
  resume_info: Record<string, any>;
  profile_classification: ProfileClassification;
  resume_id: number;
  resume_title: string;
}

export type MessageType = 
  | 'linkedin_message' 
  | 'linkedin_connection' 
  | 'linkedin_inmail' 
  | 'email_short' 
  | 'email_detailed'
  | 'ycombinator';
// Generate a message
export const generateMessage = async (
  jobDescription: string,
  messageType: MessageType,
  resumeId?: number,
  recruiterName?: string
) => {
  const response = await apiClient.post<MessageResponse>('/messages/generate', {
    job_description: jobDescription,
    message_type: messageType,
    resume_id: resumeId,
    recruiter_name: recruiterName
  });
  
  return response.data;
};