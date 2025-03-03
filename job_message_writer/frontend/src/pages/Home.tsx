import { useContext } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AuthContext } from '../context/AuthContext';

const Home = () => {
  const { isAuthenticated } = useContext(AuthContext);
  const navigate = useNavigate();

  return (
    <div className="bg-neutral-50 dark:bg-neutral-900">
      {/* Hero section */}
      <div className="relative overflow-hidden">
        <div className="max-w-7xl mx-auto">
          <div className="relative z-10 pb-8 bg-neutral-50 dark:bg-neutral-900 sm:pb-16 md:pb-20 lg:pb-28 xl:pb-32 max-w-7xl px-4 sm:px-6 lg:px-8">
            <div className="pt-10 sm:pt-16 lg:pt-8 lg:pb-14 lg:flex lg:justify-between lg:items-center">
              <div className="lg:w-1/2">
                <h1 className="text-4xl tracking-tight font-extrabold text-neutral-900 dark:text-neutral-100 sm:text-5xl md:text-6xl">
                  <span className="block xl:inline">Personalized Job Messages</span>{' '}
                  <span className="block text-primary-600 dark:text-primary-500 xl:inline">in Seconds</span>
                </h1>
                <p className="mt-3 max-w-md mx-auto text-lg text-neutral-600 dark:text-neutral-400 sm:text-xl md:mt-5 md:max-w-3xl">
                  Upload your resume once, and generate tailored messages for job applications based on any job description. Make a compelling first impression every time.
                </p>
                <div className="mt-10 sm:flex">
                  <div className="rounded-md shadow">
                    <button
                      onClick={() => navigate(isAuthenticated ? '/dashboard' : '/signup')}
                      className="w-full flex items-center justify-center px-8 py-3 border border-transparent text-base font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 md:py-4 md:text-lg md:px-10"
                    >
                      {isAuthenticated ? 'Go to Dashboard' : 'Get Started'}
                    </button>
                  </div>
                  <div className="mt-3 sm:mt-0 sm:ml-3">
                    <Link
                      to={isAuthenticated ? '/message-generator' : '/login'}
                      className="w-full flex items-center justify-center px-8 py-3 border border-transparent text-base font-medium rounded-md text-primary-700 bg-primary-100 hover:bg-primary-200 md:py-4 md:text-lg md:px-10"
                    >
                      {isAuthenticated ? 'Generate a Message' : 'Sign In'}
                    </Link>
                  </div>
                </div>
              </div>
              <div className="mt-12 lg:mt-0 lg:w-1/2">
                <div className="pl-4 -mr-40 sm:pl-6 md:-mr-16 lg:px-0 lg:m-0 lg:relative lg:h-full">
                  <img
                    className="w-full rounded-xl shadow-xl ring-1 ring-black ring-opacity-5 lg:absolute lg:left-0 lg:h-full lg:w-auto lg:max-w-none"
                    src="https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?ixlib=rb-1.2.1&auto=format&fit=crop&w=1950&q=80"
                    alt="Person typing on laptop"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Feature section */}
      <div className="py-12 bg-white dark:bg-neutral-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="lg:text-center">
            <h2 className="text-base text-primary-600 dark:text-primary-400 font-semibold tracking-wide uppercase">Features</h2>
            <p className="mt-2 text-3xl leading-8 font-bold tracking-tight text-neutral-900 dark:text-neutral-100 sm:text-4xl">
              A better way to apply for jobs
            </p>
            <p className="mt-4 max-w-2xl text-xl text-neutral-600 dark:text-neutral-400 lg:mx-auto">
              Save time and increase your chances of getting noticed with personalized, AI-generated messages.
            </p>
          </div>

          <div className="mt-10">
            <div className="space-y-10 md:space-y-0 md:grid md:grid-cols-2 md:gap-x-8 md:gap-y-10">
              {/* Feature 1 */}
              <div className="relative">
                <div className="absolute flex items-center justify-center h-12 w-12 rounded-md bg-primary-500 text-white">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" className="h-6 w-6">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                </div>
                <div className="ml-16">
                  <h3 className="text-lg leading-6 font-medium text-neutral-900 dark:text-neutral-100">Resume Analysis</h3>
                  <p className="mt-2 text-base text-neutral-600 dark:text-neutral-400">
                    Upload your resume once, and our AI will extract key information about your skills and experience.
                  </p>
                </div>
              </div>

              {/* Feature 2 */}
              <div className="relative">
                <div className="absolute flex items-center justify-center h-12 w-12 rounded-md bg-primary-500 text-white">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" className="h-6 w-6">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
                  </svg>
                </div>
                <div className="ml-16">
                  <h3 className="text-lg leading-6 font-medium text-neutral-900 dark:text-neutral-100">AI-Generated Messages</h3>
                  <p className="mt-2 text-base text-neutral-600 dark:text-neutral-400">
                    Generate personalized messages for job applications, LinkedIn, and email outreach.
                  </p>
                </div>
              </div>

              {/* Feature 3 */}
              <div className="relative">
                <div className="absolute flex items-center justify-center h-12 w-12 rounded-md bg-primary-500 text-white">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" className="h-6 w-6">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                </div>
                <div className="ml-16">
                  <h3 className="text-lg leading-6 font-medium text-neutral-900 dark:text-neutral-100">Job Description Analysis</h3>
                  <p className="mt-2 text-base text-neutral-600 dark:text-neutral-400">
                    Our AI analyzes job descriptions to match your skills with what employers are looking for.
                  </p>
                </div>
              </div>

              {/* Feature 4 */}
              <div className="relative">
                <div className="absolute flex items-center justify-center h-12 w-12 rounded-md bg-primary-500 text-white">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" className="h-6 w-6">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                </div>
                <div className="ml-16">
                  <h3 className="text-lg leading-6 font-medium text-neutral-900 dark:text-neutral-100">Time-Saving</h3>
                  <p className="mt-2 text-base text-neutral-600 dark:text-neutral-400">
                    Generate personalized messages in seconds, saving you hours of time during your job search.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Home;