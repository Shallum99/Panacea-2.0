import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { toast } from 'react-toastify';
import { getResumes, Resume } from '../api/resume';
import { generateMessage, MessageType, MessageResponse } from '../api/message';

type FormData = {
  resumeId: number;
  jobDescription: string;
  messageType: MessageType;
  recruiterName: string;
};

const MessageGenerator = () => {
  const [searchParams] = useSearchParams();
  const [isLoading, setIsLoading] = useState(false);
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [loadingResumes, setLoadingResumes] = useState(true);
  const [generatedMessage, setGeneratedMessage] = useState<MessageResponse | null>(null);
  const [copied, setCopied] = useState(false);
  
  // Form setup
  const { register, handleSubmit, setValue, formState: { errors } } = useForm<FormData>({
    defaultValues: {
      messageType: 'linkedin_message',
    },
  });

  // Load resumes
  useEffect(() => {
    const loadResumes = async () => {
      try {
        const resumeData = await getResumes();
        setResumes(resumeData);
        
        // If there's an active resume, set it as default
        const activeResume = resumeData.find(resume => resume.is_active);
        
        // Check for resumeId in URL params
        const resumeIdParam = searchParams.get('resumeId');
        
        if (resumeIdParam) {
          setValue('resumeId', parseInt(resumeIdParam));
        } else if (activeResume) {
          setValue('resumeId', activeResume.id);
        } else if (resumeData.length > 0) {
          setValue('resumeId', resumeData[0].id);
        }
      } catch (error) {
        console.error('Error loading resumes:', error);
        toast.error('Failed to load your resume profiles');
      } finally {
        setLoadingResumes(false);
      }
    };

    loadResumes();
  }, [searchParams, setValue]);

  const onSubmit = async (data: FormData) => {
    setIsLoading(true);
    try {
      const message = await generateMessage(
        data.jobDescription, 
        data.messageType, 
        data.resumeId,
        data.recruiterName || undefined // Only pass the recruiter name if it's provided
      );
      setGeneratedMessage(message);
      toast.success('Message generated successfully!');
    } catch (error) {
      console.error('Error generating message:', error);
      toast.error('Failed to generate message. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const copyToClipboard = () => {
    if (generatedMessage) {
      navigator.clipboard.writeText(generatedMessage.message);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      toast.success('Message copied to clipboard!');
    }
  };

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-neutral-900 dark:text-neutral-100">Generate Messages</h1>
        <p className="mt-2 text-neutral-600 dark:text-neutral-400">
          Create personalized messages for job applications based on your resume and the job description
        </p>
      </div>

      {/* Input Form */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-soft overflow-hidden mb-8">
        <div className="p-6 border-b border-neutral-200 dark:border-neutral-700">
          <h2 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">Message Generator</h2>
        </div>
        
        <form onSubmit={handleSubmit(onSubmit)} className="p-6 space-y-6">
          {/* Resume Selection */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label htmlFor="resumeId" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                Resume Profile
              </label>
              
              {loadingResumes ? (
                <div className="animate-pulse h-10 bg-neutral-200 dark:bg-neutral-700 rounded"></div>
              ) : resumes.length === 0 ? (
                <div className="text-sm text-red-600 dark:text-red-400">
                  No resume profiles found. Please upload a resume first.
                </div>
              ) : (
                <select
                  id="resumeId"
                  className="input w-full"
                  {...register('resumeId', { required: 'Resume profile is required' })}
                >
                  {resumes.map((resume) => (
                    <option key={resume.id} value={resume.id}>
                      {resume.title} {resume.is_active ? '(Active)' : ''}
                    </option>
                  ))}
                </select>
              )}
              {errors.resumeId && (
                <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.resumeId.message}</p>
              )}
            </div>
          
            {/* Message Type Dropdown */}
            <div>
              <label htmlFor="messageType" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                Message Type
              </label>
              <select
                id="messageType"
                className="input w-full"
                {...register('messageType', { required: 'Message type is required' })}
              >
                <optgroup label="LinkedIn">
                  <option value="linkedin_message">LinkedIn Message (300 chars)</option>
                  <option value="linkedin_connection">LinkedIn Connection (200 chars)</option>
                  <option value="linkedin_inmail">LinkedIn InMail (2000 chars)</option>
                </optgroup>
                <optgroup label="Email">
                  <option value="email_short">Short Email (1000 chars)</option>
                  <option value="email_detailed">Detailed Email (3000 chars)</option>
                </optgroup>
                <optgroup label="Other">
                  <option value="ycombinator">Y Combinator (500 chars)</option>
                </optgroup>
              </select>
              {errors.messageType && (
                <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.messageType.message}</p>
              )}
            </div>
          </div>
          
          {/* Recruiter Name (Optional) */}
          <div>
            <label htmlFor="recruiterName" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Recruiter Name (Optional)
            </label>
            <input
              id="recruiterName"
              type="text"
              className="input w-full"
              placeholder="Enter recruiter's name if known"
              {...register('recruiterName')}
            />
            <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
              If provided, the message will be personalized with the recruiter's name
            </p>
          </div>
          
          {/* Job Description */}
          <div>
            <label htmlFor="jobDescription" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Job Description
            </label>
            <textarea
              id="jobDescription"
              rows={8}
              className="input w-full"
              placeholder="Paste the full job description here..."
              {...register('jobDescription', { 
                required: 'Job description is required',
                minLength: {
                  value: 50,
                  message: 'Job description is too short. Please include more details.'
                }
              })}
            ></textarea>
            {errors.jobDescription && (
              <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.jobDescription.message}</p>
            )}
          </div>
          
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={isLoading || loadingResumes || resumes.length === 0}
              className="btn btn-primary"
            >
              {isLoading ? 'Generating...' : 'Generate Message'}
            </button>
          </div>
        </form>
      </div>
      
      {/* Generated Message Section */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-soft overflow-hidden">
        <div className="flex justify-between items-center p-6 border-b border-neutral-200 dark:border-neutral-700">
          <h2 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">Generated Message</h2>
          {generatedMessage && (
            <button
              onClick={copyToClipboard}
              className="btn btn-outline text-sm"
              disabled={copied}
            >
              {copied ? 'Copied!' : 'Copy to Clipboard'}
            </button>
          )}
        </div>
        
        {generatedMessage ? (
          <div className="p-6">
            <div className="bg-neutral-50 dark:bg-neutral-900 rounded-lg p-4 whitespace-pre-wrap font-mono text-sm">
              {generatedMessage.message}
            </div>
            
            {/* Company Info */}
            <div className="mt-6">
              <h3 className="text-sm font-medium text-neutral-900 dark:text-neutral-100 mb-2">Company Information</h3>
              <div className="text-xs text-neutral-600 dark:text-neutral-400 space-y-1">
                <p><strong>Company:</strong> {generatedMessage.company_info.company_name}</p>
                <p><strong>Industry:</strong> {generatedMessage.company_info.industry}</p>
                <p><strong>Size:</strong> {generatedMessage.company_info.company_size}</p>
                <p><strong>Location:</strong> {generatedMessage.company_info.location}</p>
              </div>
            </div>
            
            {/* Resume used */}
            <div className="mt-4">
              <h3 className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
                Based on: {generatedMessage.resume_title}
              </h3>
            </div>
          </div>
        ) : (
          <div className="p-10 text-center">
            <svg xmlns="http://www.w3.org/2000/svg" className="mx-auto h-12 w-12 text-neutral-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
            <h3 className="mt-2 text-lg font-medium text-neutral-900 dark:text-neutral-100">No message generated yet</h3>
            <p className="mt-1 text-neutral-600 dark:text-neutral-400">
              Fill out the form above to generate a personalized message
            </p>
          </div>
        )}
      </div>
      
      {/* Tips */}
      <div className="mt-8 bg-white dark:bg-neutral-800 rounded-lg shadow-soft overflow-hidden">
        <div className="p-6 border-b border-neutral-200 dark:border-neutral-700">
          <h2 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">Tips for Success</h2>
        </div>
        <div className="p-6">
          <ul className="space-y-4 text-sm">
            <li className="flex">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-primary-600 mr-2 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="text-neutral-700 dark:text-neutral-300">
                <strong>Paste the full job description</strong> for the best results. More details help generate a more personalized message.
              </span>
            </li>
            <li className="flex">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-primary-600 mr-2 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="text-neutral-700 dark:text-neutral-300">
                <strong>Choose the right message type</strong> based on where you're applying. LinkedIn messages should be shorter and more direct.
              </span>
            </li>
            <li className="flex">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-primary-600 mr-2 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="text-neutral-700 dark:text-neutral-300">
                <strong>Review and customize</strong> the generated message before sending. Add a personal touch or adjust details as needed.
              </span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
};

export default MessageGenerator;