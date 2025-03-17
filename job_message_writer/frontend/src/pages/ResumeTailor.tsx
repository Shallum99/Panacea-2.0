import React, { useState, useEffect } from 'react';
import { toast } from 'react-toastify';
import { getResumes, Resume } from '../api/resume';
import { 
  optimizeResume, 
  calculateATSScore, 
  ResumeSection, 
  ResumeTailorResponse,
  ATSScoreResponse
} from '../api/resumeTailor';
import ATSScoreDisplay from '../components/resume/ATSScoreDisplay';
import OptimizeSection from '../components/resume/OptimizeSection';

const ResumeTailor: React.FC = () => {
  // State
  const [jobDescription, setJobDescription] = useState<string>('');
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [selectedResumeId, setSelectedResumeId] = useState<number | null>(null);
  const [sectionsToOptimize, setSectionsToOptimize] = useState<ResumeSection[]>([]);
  const [optimizationResults, setOptimizationResults] = useState<ResumeTailorResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [initialATSScore, setInitialATSScore] = useState<ATSScoreResponse | null>(null);
  const [calculatingInitialScore, setCalculatingInitialScore] = useState<boolean>(false);
  
  // Load resumes when the component mounts
  useEffect(() => {
    const loadResumes = async () => {
      try {
        const resumeData = await getResumes();
        setResumes(resumeData);
        
        // Set first resume as selected by default if available
        if (resumeData.length > 0) {
          const activeResume = resumeData.find(r => r.is_active) || resumeData[0];
          setSelectedResumeId(activeResume.id);
        }
      } catch (error) {
        console.error('Error loading resumes:', error);
        toast.error('Failed to load your resume profiles');
      }
    };

    loadResumes();
  }, []);

  // Handle section toggle
  const handleSectionToggle = (section: ResumeSection) => {
    setSectionsToOptimize(prev => {
      if (prev.includes(section)) {
        return prev.filter(s => s !== section);
      } else {
        return [...prev, section];
      }
    });
  };

  // Handle job description change
  const handleJobDescriptionChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setJobDescription(e.target.value);
    setOptimizationResults(null); // Reset results when job description changes
    setInitialATSScore(null); // Reset initial score
  };

  // Handle resume selection change
  const handleResumeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const resumeId = parseInt(e.target.value);
    setSelectedResumeId(resumeId);
    setOptimizationResults(null); // Reset results when resume changes
    setInitialATSScore(null); // Reset initial score
  };

  // Calculate initial ATS score
  const handleCalculateInitialScore = async () => {
    if (!selectedResumeId || !jobDescription) {
      toast.error('Please select a resume and provide a job description');
      return;
    }

    setCalculatingInitialScore(true);
    try {
      const selectedResume = resumes.find(r => r.id === selectedResumeId);
      if (!selectedResume) {
        throw new Error('Selected resume not found');
      }

      // Assuming you have a way to get resume content
      // This might need adaptation based on your actual API structure
      const response = await calculateATSScore(
        jobDescription,
        selectedResume.content || ''
      );
      
      setInitialATSScore(response);
      toast.success('ATS score calculated successfully');
    } catch (error) {
      console.error('Error calculating ATS score:', error);
      toast.error('Failed to calculate ATS score');
    } finally {
      setCalculatingInitialScore(false);
    }
  };

  // Handle optimization
  const handleOptimize = async () => {
    if (!selectedResumeId || !jobDescription || sectionsToOptimize.length === 0) {
      toast.error('Please select a resume, provide a job description, and choose at least one section to optimize');
      return;
    }

    setIsLoading(true);
    try {
      const response = await optimizeResume(
        jobDescription,
        selectedResumeId,
        sectionsToOptimize
      );
      
      setOptimizationResults(response);
      toast.success('Resume optimization completed');
    } catch (error) {
      console.error('Error optimizing resume:', error);
      toast.error('Failed to optimize resume');
    } finally {
      setIsLoading(false);
    }
  };

  // Handle copying content
  const handleCopyContent = (content: string) => {
    // This function is passed to OptimizeSection component
    // Any additional logic after copying can be added here
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-neutral-900 dark:text-neutral-100">Resume Tailor</h1>
        <p className="mt-2 text-neutral-600 dark:text-neutral-400">
          Optimize your resume for specific job descriptions and improve your ATS score
        </p>
      </div>

      {/* Input Section */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-soft overflow-hidden mb-8">
        <div className="p-6 border-b border-neutral-200 dark:border-neutral-700">
          <h2 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">Optimize Your Resume</h2>
        </div>
        
        <div className="p-6 space-y-6">
          {/* Resume Selection */}
          <div>
            <label htmlFor="resume-select" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Select Resume Profile
            </label>
            <select
              id="resume-select"
              className="input w-full"
              value={selectedResumeId || ''}
              onChange={handleResumeChange}
              disabled={isLoading || calculatingInitialScore}
            >
              <option value="" disabled>Select a resume</option>
              {resumes.map(resume => (
                <option key={resume.id} value={resume.id}>
                  {resume.title} {resume.is_active ? '(Active)' : ''}
                </option>
              ))}
            </select>
          </div>
          
          {/* Job Description */}
          <div>
            <label htmlFor="job-description" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Job Description
            </label>
            <textarea
              id="job-description"
              rows={8}
              className="input w-full"
              placeholder="Paste the job description here..."
              value={jobDescription}
              onChange={handleJobDescriptionChange}
              disabled={isLoading || calculatingInitialScore}
            ></textarea>
          </div>
          
          {/* Section Selection */}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
              Sections to Optimize
            </label>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {Object.values(ResumeSection).map(section => (
                <div key={section} className="flex items-center">
                  <input
                    id={`section-${section}`}
                    type="checkbox"
                    className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-neutral-300 rounded"
                    checked={sectionsToOptimize.includes(section)}
                    onChange={() => handleSectionToggle(section)}
                    disabled={isLoading || calculatingInitialScore}
                  />
                  <label htmlFor={`section-${section}`} className="ml-2 block text-sm text-neutral-700 dark:text-neutral-300">
                    {section}
                  </label>
                </div>
              ))}
            </div>
          </div>
          
          {/* Action Buttons */}
          <div className="flex flex-col md:flex-row md:justify-between gap-4">
            <button
              onClick={handleCalculateInitialScore}
              disabled={!selectedResumeId || !jobDescription || isLoading || calculatingInitialScore}
              className="btn btn-outline"
            >
              {calculatingInitialScore ? 'Calculating...' : 'Calculate Current ATS Score'}
            </button>
            
            <button
              onClick={handleOptimize}
              disabled={!selectedResumeId || !jobDescription || sectionsToOptimize.length === 0 || isLoading || calculatingInitialScore}
              className="btn btn-primary"
            >
              {isLoading ? 'Optimizing...' : 'Optimize Resume'}
            </button>
          </div>
        </div>
      </div>

      {/* Initial ATS Score Display */}
      {initialATSScore && !optimizationResults && (
        <div className="mb-8">
          <ATSScoreDisplay
            originalScore={initialATSScore.score}
            optimizedScore={initialATSScore.score}
            breakdown={initialATSScore.breakdown}
            suggestions={initialATSScore.suggestions}
          />
        </div>
      )}
      
      {/* Results Section */}
      {optimizationResults && (
        <div className="space-y-8">
          <ATSScoreDisplay
            originalScore={optimizationResults.originalATSScore}
            optimizedScore={optimizationResults.optimizedATSScore}
            breakdown={optimizationResults.optimizedSections ? {} : undefined}
            suggestions={[]}
          />
          
          {Object.entries(optimizationResults.optimizedSections).map(([section, content]) => (
            <OptimizeSection
              key={section}
              title={section}
              originalContent={content.original}
              optimizedContent={content.optimized}
              onCopy={handleCopyContent}
            />
          ))}
        </div>
      )}
      
      {/* Tips Section */}
      <div className="mt-8 bg-white dark:bg-neutral-800 rounded-lg shadow-soft overflow-hidden">
        <div className="p-6 border-b border-neutral-200 dark:border-neutral-700">
          <h2 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">Resume Optimization Tips</h2>
        </div>
        <div className="p-6">
          <ul className="space-y-4 text-sm">
            <li className="flex">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-primary-600 mr-2 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="text-neutral-700 dark:text-neutral-300">
                <strong>Use keywords from the job description</strong> - ATS systems scan for job-specific keywords.
              </span>
            </li>
            <li className="flex">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-primary-600 mr-2 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="text-neutral-700 dark:text-neutral-300">
                <strong>Be specific with skills and experience</strong> - Quantify achievements and use action verbs.
              </span>
            </li>
            <li className="flex">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-primary-600 mr-2 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="text-neutral-700 dark:text-neutral-300">
                <strong>Keep formatting simple</strong> - Complex layouts and graphics can confuse ATS systems.
              </span>
            </li>
            <li className="flex">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-primary-600 mr-2 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="text-neutral-700 dark:text-neutral-300">
                <strong>Tailor for each application</strong> - Update your resume for each specific job application.
              </span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
};

export default ResumeTailor;