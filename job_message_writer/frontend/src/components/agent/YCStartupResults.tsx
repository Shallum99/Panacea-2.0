import { useState } from 'react';
import { YCStartup, Founder, OutreachEmail } from '../../types/agent';

interface YCStartupResultsProps {
  startups: YCStartup[];
  founders: Founder[];
  outreach: OutreachEmail[];
}

const YCStartupResults = ({ startups, founders, outreach }: YCStartupResultsProps) => {
  const [selectedStartup, setSelectedStartup] = useState<string | null>(null);

  const getFoundersForStartup = (startupId: string) => {
    return founders.filter(f => f.startupId === startupId);
  };

  const getOutreachForFounder = (founderId: string) => {
    return outreach.find(o => o.founderId === founderId);
  };

  const getStatusColor = (status: OutreachEmail['status']) => {
    const colors = {
      queued: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
      sent: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
      delivered: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900 dark:text-cyan-300',
      opened: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300',
      replied: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
      failed: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
    };
    return colors[status] || colors.queued;
  };

  const getEmailConfidenceBadge = (confidence?: 'high' | 'medium' | 'low') => {
    if (!confidence) return null;

    const colors = {
      high: 'bg-green-500',
      medium: 'bg-yellow-500',
      low: 'bg-orange-500',
    };

    return (
      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium text-white ${colors[confidence]}`}>
        {confidence} confidence
      </span>
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white flex items-center">
          <svg className="w-5 h-5 mr-2 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
          </svg>
          YC Startups Found
        </h3>
        <span className="text-sm text-gray-400">
          {startups.length} companies
        </span>
      </div>

      <div className="grid grid-cols-1 gap-4">
        {startups.map((startup) => {
          const startupFounders = getFoundersForStartup(startup.id);
          const isExpanded = selectedStartup === startup.id;

          return (
            <div
              key={startup.id}
              className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-xl border border-slate-700 hover:border-slate-600 transition-all duration-200 overflow-hidden"
            >
              {/* Startup Header */}
              <div className="p-6">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center space-x-3">
                      {startup.logoUrl ? (
                        <img
                          src={startup.logoUrl}
                          alt={`${startup.name} logo`}
                          className="w-12 h-12 rounded-lg object-cover"
                        />
                      ) : (
                        <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
                          <span className="text-white font-bold text-lg">
                            {startup.name.charAt(0)}
                          </span>
                        </div>
                      )}

                      <div>
                        <h4 className="text-lg font-semibold text-white">
                          {startup.name}
                        </h4>
                        <div className="flex items-center space-x-2 mt-1">
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200">
                            {startup.batch}
                          </span>
                          <span className="text-sm text-gray-400">
                            {startup.industry}
                          </span>
                        </div>
                      </div>
                    </div>

                    <p className="mt-3 text-sm text-gray-300">
                      {startup.description}
                    </p>

                    {startup.tags.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {startup.tags.map((tag, index) => (
                          <span
                            key={index}
                            className="inline-flex items-center px-2 py-1 rounded-md text-xs font-medium bg-slate-700 text-slate-300"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  <button
                    onClick={() => setSelectedStartup(isExpanded ? null : startup.id)}
                    className="ml-4 p-2 rounded-lg hover:bg-slate-700 transition-colors"
                  >
                    <svg
                      className={`w-5 h-5 text-gray-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                </div>
              </div>

              {/* Expanded Founders Section */}
              {isExpanded && (
                <div className="border-t border-slate-700 bg-slate-900/50 p-6">
                  <h5 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-4">
                    Founders ({startupFounders.length})
                  </h5>

                  <div className="space-y-4">
                    {startupFounders.map((founder) => {
                      const founderOutreach = getOutreachForFounder(founder.id);

                      return (
                        <div
                          key={founder.id}
                          className="bg-slate-800 rounded-lg p-4 border border-slate-700"
                        >
                          <div className="flex items-start justify-between">
                            <div className="flex-1">
                              <div className="flex items-center space-x-2">
                                <h6 className="text-base font-medium text-white">
                                  {founder.name}
                                </h6>
                                <span className="text-sm text-gray-400">
                                  • {founder.role}
                                </span>
                              </div>

                              {founder.email && (
                                <div className="mt-2 flex items-center space-x-2">
                                  <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                                  </svg>
                                  <span className="text-sm text-gray-300">{founder.email}</span>
                                  {getEmailConfidenceBadge(founder.emailConfidence)}
                                </div>
                              )}

                              {founder.linkedinUrl && (
                                <a
                                  href={founder.linkedinUrl}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="mt-2 inline-flex items-center text-sm text-blue-400 hover:text-blue-300"
                                >
                                  <svg className="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 24 24">
                                    <path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z" />
                                  </svg>
                                  LinkedIn Profile
                                </a>
                              )}
                            </div>

                            {founderOutreach && (
                              <div className="ml-4">
                                <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-medium ${getStatusColor(founderOutreach.status)}`}>
                                  {founderOutreach.status}
                                </span>
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {startup.website && (
                    <div className="mt-4 pt-4 border-t border-slate-700">
                      <a
                        href={startup.website}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center text-sm text-blue-400 hover:text-blue-300"
                      >
                        <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                        </svg>
                        Visit Website
                      </a>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default YCStartupResults;
