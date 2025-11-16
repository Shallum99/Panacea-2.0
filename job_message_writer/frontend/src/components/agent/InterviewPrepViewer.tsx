import { useState } from 'react';
import { InterviewPrep } from '../../types/agent';
import ReactMarkdown from 'react-markdown';

interface InterviewPrepViewerProps {
  interviewPrep: InterviewPrep;
  startupName: string;
}

const InterviewPrepViewer = ({ interviewPrep, startupName }: InterviewPrepViewerProps) => {
  const [activeTab, setActiveTab] = useState<'research' | 'founders' | 'questions'>('research');

  const tabs = [
    { id: 'research', name: 'Company Research', icon: '🏢' },
    { id: 'founders', name: 'Founder Insights', icon: '👥' },
    { id: 'questions', name: 'Interview Questions', icon: '💭' },
  ] as const;

  const categoryColors = {
    technical: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
    behavioral: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
    'company-specific': 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  };

  return (
    <div className="bg-gradient-to-br from-slate-900 to-slate-800 rounded-2xl shadow-2xl border border-slate-700 overflow-hidden">
      {/* Header */}
      <div className="bg-gradient-to-r from-indigo-600 to-purple-600 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-white flex items-center">
              <svg className="w-7 h-7 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              Interview Prep: {startupName}
            </h2>
            <p className="mt-1 text-indigo-100">
              Generated on {new Date(interviewPrep.generatedAt).toLocaleDateString()}
            </p>
          </div>

          <button
            className="px-4 py-2 bg-white/20 hover:bg-white/30 text-white rounded-lg transition-colors flex items-center space-x-2"
            onClick={() => window.print()}
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
            </svg>
            <span>Print</span>
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-slate-700 bg-slate-900/50">
        <div className="flex space-x-1 px-6">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-6 py-4 font-medium text-sm transition-all relative ${
                activeTab === tab.id
                  ? 'text-white'
                  : 'text-gray-400 hover:text-gray-300'
              }`}
            >
              <span className="flex items-center space-x-2">
                <span>{tab.icon}</span>
                <span>{tab.name}</span>
              </span>
              {activeTab === tab.id && (
                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-indigo-500 to-purple-500"></div>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="p-6">
        {/* Company Research Tab */}
        {activeTab === 'research' && (
          <div className="space-y-6">
            {/* Mission */}
            <div className="bg-slate-800/50 rounded-xl p-5 border border-slate-700">
              <h3 className="text-lg font-semibold text-white mb-3 flex items-center">
                <svg className="w-5 h-5 mr-2 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                Mission & Vision
              </h3>
              <div className="prose prose-invert prose-sm max-w-none">
                <ReactMarkdown>{interviewPrep.companyResearch.mission}</ReactMarkdown>
              </div>
            </div>

            {/* Product Analysis */}
            <div className="bg-slate-800/50 rounded-xl p-5 border border-slate-700">
              <h3 className="text-lg font-semibold text-white mb-3 flex items-center">
                <svg className="w-5 h-5 mr-2 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
                Product Analysis
              </h3>
              <div className="prose prose-invert prose-sm max-w-none">
                <ReactMarkdown>{interviewPrep.companyResearch.productAnalysis}</ReactMarkdown>
              </div>
            </div>

            {/* Tech Stack */}
            {interviewPrep.companyResearch.techStack.length > 0 && (
              <div className="bg-slate-800/50 rounded-xl p-5 border border-slate-700">
                <h3 className="text-lg font-semibold text-white mb-3 flex items-center">
                  <svg className="w-5 h-5 mr-2 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                  </svg>
                  Tech Stack
                </h3>
                <div className="flex flex-wrap gap-2">
                  {interviewPrep.companyResearch.techStack.map((tech, index) => (
                    <span
                      key={index}
                      className="px-3 py-1.5 bg-blue-500/20 text-blue-300 rounded-lg text-sm font-medium border border-blue-500/30"
                    >
                      {tech}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Recent News */}
            {interviewPrep.companyResearch.recentNews.length > 0 && (
              <div className="bg-slate-800/50 rounded-xl p-5 border border-slate-700">
                <h3 className="text-lg font-semibold text-white mb-3 flex items-center">
                  <svg className="w-5 h-5 mr-2 text-yellow-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z" />
                  </svg>
                  Recent News
                </h3>
                <ul className="space-y-2">
                  {interviewPrep.companyResearch.recentNews.map((news, index) => (
                    <li key={index} className="flex items-start space-x-2 text-gray-300">
                      <span className="text-yellow-400 mt-1">•</span>
                      <span className="text-sm">{news}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Competitors */}
            {interviewPrep.companyResearch.competitors.length > 0 && (
              <div className="bg-slate-800/50 rounded-xl p-5 border border-slate-700">
                <h3 className="text-lg font-semibold text-white mb-3 flex items-center">
                  <svg className="w-5 h-5 mr-2 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                  Competitors
                </h3>
                <div className="flex flex-wrap gap-2">
                  {interviewPrep.companyResearch.competitors.map((competitor, index) => (
                    <span
                      key={index}
                      className="px-3 py-1.5 bg-red-500/20 text-red-300 rounded-lg text-sm font-medium border border-red-500/30"
                    >
                      {competitor}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Founder Insights Tab */}
        {activeTab === 'founders' && (
          <div className="space-y-6">
            {interviewPrep.founderInsights.map((founder, index) => (
              <div
                key={founder.founderId}
                className="bg-slate-800/50 rounded-xl p-5 border border-slate-700"
              >
                <h3 className="text-lg font-semibold text-white mb-4 flex items-center">
                  <div className="w-10 h-10 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center mr-3">
                    <span className="text-white font-bold">
                      {String.fromCharCode(65 + index)}
                    </span>
                  </div>
                  Founder #{index + 1}
                </h3>

                <div className="space-y-4">
                  <div>
                    <h4 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-2">
                      Background
                    </h4>
                    <div className="prose prose-invert prose-sm max-w-none">
                      <ReactMarkdown>{founder.background}</ReactMarkdown>
                    </div>
                  </div>

                  {founder.education && (
                    <div>
                      <h4 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-2">
                        Education
                      </h4>
                      <p className="text-gray-300">{founder.education}</p>
                    </div>
                  )}

                  {founder.previousCompanies.length > 0 && (
                    <div>
                      <h4 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-2">
                        Previous Companies
                      </h4>
                      <div className="flex flex-wrap gap-2">
                        {founder.previousCompanies.map((company, idx) => (
                          <span
                            key={idx}
                            className="px-3 py-1.5 bg-purple-500/20 text-purple-300 rounded-lg text-sm border border-purple-500/30"
                          >
                            {company}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {founder.interests.length > 0 && (
                    <div>
                      <h4 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-2">
                        Interests
                      </h4>
                      <div className="flex flex-wrap gap-2">
                        {founder.interests.map((interest, idx) => (
                          <span
                            key={idx}
                            className="px-3 py-1.5 bg-indigo-500/20 text-indigo-300 rounded-lg text-sm border border-indigo-500/30"
                          >
                            {interest}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Interview Questions Tab */}
        {activeTab === 'questions' && (
          <div className="space-y-4">
            {interviewPrep.interviewQuestions.map((question, index) => (
              <div
                key={index}
                className="bg-slate-800/50 rounded-xl p-5 border border-slate-700"
              >
                <div className="flex items-start justify-between mb-3">
                  <h3 className="text-lg font-medium text-white flex items-start">
                    <span className="text-indigo-400 mr-3 font-bold">Q{index + 1}.</span>
                    <span>{question.question}</span>
                  </h3>
                  <span
                    className={`px-2.5 py-1 rounded-lg text-xs font-medium border ${
                      categoryColors[question.category]
                    }`}
                  >
                    {question.category}
                  </span>
                </div>

                <div className="ml-8">
                  <h4 className="text-sm font-medium text-emerald-400 mb-2">
                    Suggested Answer:
                  </h4>
                  <div className="prose prose-invert prose-sm max-w-none text-gray-300">
                    <ReactMarkdown>{question.suggestedAnswer}</ReactMarkdown>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default InterviewPrepViewer;
