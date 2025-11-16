// Agent-related types and interfaces

export interface AgentMessage {
  id: string;
  type: 'user' | 'agent' | 'system';
  content: string;
  timestamp: Date;
  metadata?: {
    status?: AgentStatus;
    progress?: number;
  };
}

export type AgentStatus =
  | 'idle'
  | 'searching_startups'
  | 'extracting_founders'
  | 'validating_emails'
  | 'sending_outreach'
  | 'generating_interview_prep'
  | 'completed'
  | 'error';

export interface YCStartup {
  id: string;
  name: string;
  batch: string;
  description: string;
  website: string;
  industry: string;
  tags: string[];
  logoUrl?: string;
  founded: string;
}

export interface Founder {
  id: string;
  name: string;
  role: string;
  linkedinUrl?: string;
  email?: string;
  emailConfidence?: 'high' | 'medium' | 'low';
  startupId: string;
}

export interface OutreachEmail {
  id: string;
  founderId: string;
  startupId: string;
  subject: string;
  body: string;
  status: 'queued' | 'sent' | 'delivered' | 'opened' | 'replied' | 'failed';
  sentAt?: Date;
  repliedAt?: Date;
  error?: string;
}

export interface InterviewPrep {
  id: string;
  startupId: string;
  companyResearch: {
    mission: string;
    recentNews: string[];
    productAnalysis: string;
    techStack: string[];
    competitors: string[];
  };
  founderInsights: {
    founderId: string;
    background: string;
    previousCompanies: string[];
    education: string;
    interests: string[];
  }[];
  interviewQuestions: {
    question: string;
    suggestedAnswer: string;
    category: 'technical' | 'behavioral' | 'company-specific';
  }[];
  generatedAt: Date;
}

export interface AgentRun {
  id: string;
  goal: string;
  status: AgentStatus;
  startedAt: Date;
  completedAt?: Date;
  stats: {
    startupsFound: number;
    foundersExtracted: number;
    emailsValidated: number;
    emailsSent: number;
    repliesReceived: number;
    interviewsScheduled: number;
  };
  startups?: YCStartup[];
  founders?: Founder[];
  outreach?: OutreachEmail[];
  interviewPreps?: InterviewPrep[];
}

export interface AgentStep {
  id: string;
  name: string;
  status: 'pending' | 'in_progress' | 'completed' | 'error';
  description: string;
  startedAt?: Date;
  completedAt?: Date;
  error?: string;
}
