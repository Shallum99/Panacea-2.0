import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { getResumes, setActiveResume, Resume } from '../api/resume';

const Dashboard = () => {
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    const loadResumes = async () => {
      try {
        const resumeData = await getResumes();
        setResumes(resumeData);
      } catch (error) {
        console.error('Error loading resumes:', error);
        toast.error('Failed to load your resume profiles');
      } finally {
        setIsLoading(false);
      }
    };

    loadResumes();
  }, []);

  const handleSetActive = async (resumeId: number) => {
    try {
      await setActiveResume(resumeId);
      // Update local state
      setResumes(prevResumes => 
        prevResumes.map(resume => ({
          ...resume,
          is_active: resume.id === resumeId
        }))
      );
      toast.success('Active profile updated!');
    } catch (error) {
      console.error('Error setting active resume:', error);
      toast.error('Failed to update active profile');
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-neutral-900 dark:text-neutral-100">Dashboard</h1>
        <p className="mt-2 text-neutral-600 dark:text-neutral-400">
          Manage your resume profiles and generate personalized messages
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Resume Profiles Section */}
        <div className="lg:col-span-2">
          <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-soft overflow-hidden">
            <div className="flex justify-between items-center p-6 border-b border-neutral-200 dark:border-neutral-700">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">Your Resume Profiles</h2>
              <button
                onClick={() => navigate('/resume-upload')}
                className="btn btn-primary"
              >
                Upload New Resume
              </button>
            </div>
            
            {isLoading ? (
              <div className="p-6 flex justify-center">
                <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-b-2 border-primary-600"></div>
              </div>
            ) : resumes.length === 0 ? (
              <div className="p-10 text-center">
                <svg xmlns="http://www.w3.org/2000/svg" className="mx-auto h-12 w-12 text-neutral-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <h3 className="mt-2 text-lg font-medium text-neutral-900 dark:text-neutral-100">No resumes found</h3>
                <p className="mt-1 text-neutral-600 dark:text-neutral-400">
                  Upload your first resume to get started
                </p>
                <div className="mt-6">
                  <button
                    onClick={() => navigate('/resume-upload')}
                    className="btn btn-primary"
                  >
                    Upload Resume
                  </button>
                </div>
              </div>
            ) : (
              <div className="divide-y divide-neutral-200 dark:divide-neutral-700">
                {resumes.map(resume => (
                  <div key={resume.id} className="p-6">
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="flex items-center">
                          <h3 className="text-lg font-medium text-neutral-900 dark:text-neutral-100">
                            {resume.title}
                          </h3>
                          {resume.is_active && (
                            <span className="ml-2 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
                              Active
                            </span>
                          )}
                        </div>
                        <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
                          {resume.filename}
                        </p>
                        
                        <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-4">
                          <div>
                            <h4 className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                              Profile Type
                            </h4>
                            <p className="mt-1 text-sm text-neutral-900 dark:text-neutral-100">
                              {resume.profile_classification.profile_type || 'Not specified'}
                            </p>
                          </div>
                          
                          <div>
                            <h4 className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                              Experience
                            </h4>
                            <p className="mt-1 text-sm text-neutral-900 dark:text-neutral-100">
                              {resume.profile_classification.years_experience || 'Not specified'} - {resume.profile_classification.seniority || 'Not specified'}
                            </p>
                          </div>
                          
                          <div>
                            <h4 className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                              Primary Languages
                            </h4>
                            <div className="mt-1 flex flex-wrap gap-1">
                              {resume.profile_classification.primary_languages.length > 0 ? (
                                resume.profile_classification.primary_languages.map((lang, index) => (
                                  <span 
                                    key={index}
                                    className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-primary-100 text-primary-800 dark:bg-primary-900 dark:text-primary-200"
                                  >
                                    {lang}
                                  </span>
                                ))
                              ) : (
                                <span className="text-sm text-neutral-600 dark:text-neutral-400">Not specified</span>
                              )}
                            </div>
                          </div>
                          
                          <div>
                            <h4 className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                              Frameworks
                            </h4>
                            <div className="mt-1 flex flex-wrap gap-1">
                              {resume.profile_classification.frameworks.length > 0 ? (
                                resume.profile_classification.frameworks.map((framework, index) => (
                                  <span 
                                    key={index}
                                    className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-secondary-100 text-secondary-800 dark:bg-secondary-900 dark:text-secondary-200"
                                  >
                                    {framework}
                                  </span>
                                ))
                              ) : (
                                <span className="text-sm text-neutral-600 dark:text-neutral-400">Not specified</span>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                      
                      <div className="flex space-x-3">
                        {!resume.is_active && (
                          <button
                            onClick={() => handleSetActive(resume.id)}
                            className="btn btn-outline text-sm"
                          >
                            Set as Active
                          </button>
                        )}
                        
                        <button
                          onClick={() => navigate(`/message-generator?resumeId=${resume.id}`)}
                          className="btn btn-primary text-sm"
                        >
                          Generate Messages
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
        
        {/* Quick Actions & Stats Section */}
        <div className="space-y-6">
          {/* Quick Actions */}
          <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-soft overflow-hidden">
            <div className="p-6 border-b border-neutral-200 dark:border-neutral-700">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">Quick Actions</h2>
            </div>
            <div className="p-6 space-y-4">
              <button
                onClick={() => navigate('/message-generator')}
                className="w-full btn btn-primary py-3 flex items-center justify-center"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2" viewBox="0 0 20 20" fill="currentColor">
                  <path d="M2 5a2 2 0 012-2h7a2 2 0 012 2v4a2 2 0 01-2 2H9l-3 3v-3H4a2 2 0 01-2-2V5z" />
                  <path d="M15 7v2a4 4 0 01-4 4H9.828l-1.766 1.767c.28.149.599.233.938.233h2l3 3v-3h2a2 2 0 002-2V9a2 2 0 00-2-2h-1z" />
                </svg>
                Generate New Message
              </button>
              
              <button
                onClick={() => navigate('/resume-upload')}
                className="w-full btn btn-outline py-3 flex items-center justify-center"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM6.293 6.707a1 1 0 010-1.414l3-3a1 1 0 011.414 0l3 3a1 1 0 01-1.414 1.414L11 5.414V13a1 1 0 11-2 0V5.414L7.707 6.707a1 1 0 01-1.414 0z" clipRule="evenodd" />
                </svg>
                Upload New Resume
              </button>
            </div>
          </div>
          
          {/* Stats */}
          <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-soft overflow-hidden">
            <div className="p-6 border-b border-neutral-200 dark:border-neutral-700">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">Your Stats</h2>
            </div>
            <div className="p-6">
              <dl className="grid grid-cols-1 gap-6">
                <div className="bg-neutral-50 dark:bg-neutral-700 rounded-lg p-4">
                  <dt className="text-sm font-medium text-neutral-500 dark:text-neutral-400 truncate">
                    Resume Profiles
                  </dt>
                  <dd className="mt-1 text-3xl font-semibold text-primary-600 dark:text-primary-400">
                    {resumes.length}
                  </dd>
                </div>
                
                <div className="bg-neutral-50 dark:bg-neutral-700 rounded-lg p-4">
                  <dt className="text-sm font-medium text-neutral-500 dark:text-neutral-400 truncate">
                    Messages Generated
                  </dt>
                  <dd className="mt-1 text-3xl font-semibold text-primary-600 dark:text-primary-400">
                    0
                  </dd>
                </div>
              </dl>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;