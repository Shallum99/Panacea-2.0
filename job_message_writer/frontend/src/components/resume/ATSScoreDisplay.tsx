import React from 'react';

interface ATSScoreDisplayProps {
  originalScore: number;
  optimizedScore: number;
  breakdown?: Record<string, number>;
  suggestions?: string[];
}

const ATSScoreDisplay: React.FC<ATSScoreDisplayProps> = ({
  originalScore,
  optimizedScore,
  breakdown = {},
  suggestions = []
}) => {
  const renderScoreGauge = (score: number, label: string) => {
    // Determine color based on score
    let colorClass = 'bg-red-500';
    if (score >= 80) {
      colorClass = 'bg-green-500';
    } else if (score >= 60) {
      colorClass = 'bg-yellow-500';
    } else if (score >= 40) {
      colorClass = 'bg-orange-500';
    }

    return (
      <div className="flex flex-col items-center">
        <div className="text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          {label}
        </div>
        <div className="relative h-32 w-32">
          <svg viewBox="0 0 100 100" className="h-full w-full">
            {/* Background circle */}
            <circle
              cx="50"
              cy="50"
              r="45"
              fill="none"
              stroke="#e5e7eb"
              strokeWidth="8"
              className="dark:stroke-neutral-700"
            />
            {/* Score circle */}
            <circle
              cx="50"
              cy="50"
              r="45"
              fill="none"
              stroke={colorClass.replace('bg-', 'text-')}
              strokeWidth="8"
              strokeDasharray={`${score * 2.83} 283`}
              strokeDashoffset="0"
              transform="rotate(-90 50 50)"
              className={colorClass.replace('bg-', 'stroke-')}
            />
            {/* Score text */}
            <text
              x="50"
              y="55"
              textAnchor="middle"
              fontSize="24"
              fontWeight="bold"
              className="fill-neutral-900 dark:fill-neutral-100"
            >
              {score}%
            </text>
          </svg>
        </div>
      </div>
    );
  };

  const renderBreakdown = () => {
    if (!breakdown || Object.keys(breakdown).length === 0) {
      return null;
    }

    return (
      <div className="mt-6">
        <h3 className="text-md font-medium text-neutral-900 dark:text-neutral-100 mb-3">Score Breakdown</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Object.entries(breakdown).map(([category, score]) => (
            <div key={category} className="bg-neutral-50 dark:bg-neutral-800 rounded-lg p-3">
              <div className="flex justify-between items-center mb-1">
                <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                  {category}
                </span>
                <span className="text-sm font-medium text-neutral-900 dark:text-neutral-100">
                  {score}%
                </span>
              </div>
              <div className="w-full bg-neutral-200 dark:bg-neutral-700 rounded-full h-2">
                <div
                  className={`h-2 rounded-full ${score >= 80 ? 'bg-green-500' : score >= 60 ? 'bg-yellow-500' : score >= 40 ? 'bg-orange-500' : 'bg-red-500'}`}
                  style={{ width: `${score}%` }}
                ></div>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  const renderSuggestions = () => {
    if (!suggestions || suggestions.length === 0) {
      return null;
    }

    return (
      <div className="mt-6">
        <h3 className="text-md font-medium text-neutral-900 dark:text-neutral-100 mb-3">Improvement Suggestions</h3>
        <ul className="bg-neutral-50 dark:bg-neutral-800 rounded-lg p-4 text-sm text-neutral-700 dark:text-neutral-300 space-y-2">
          {suggestions.map((suggestion, index) => (
            <li key={index} className="flex items-start">
              <span className="mr-2 mt-0.5 text-primary-600 dark:text-primary-400">•</span>
              <span>{suggestion}</span>
            </li>
          ))}
        </ul>
      </div>
    );
  };

  const improvementPercentage = originalScore > 0 
    ? Math.round(((optimizedScore - originalScore) / originalScore) * 100) 
    : 0;

  return (
    <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-soft overflow-hidden">
      <div className="p-6 border-b border-neutral-200 dark:border-neutral-700">
        <h2 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">ATS Score Analysis</h2>
      </div>
      <div className="p-6">
        <div className="flex flex-col md:flex-row justify-center gap-8 mb-6">
          {renderScoreGauge(originalScore, 'Original Score')}
          
          {/* Improvement indicator */}
          {improvementPercentage > 0 && (
            <div className="flex items-center">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
              </svg>
              <div className="text-green-500 font-bold text-lg">
                +{improvementPercentage}%
              </div>
            </div>
          )}
          
          {renderScoreGauge(optimizedScore, 'Optimized Score')}
        </div>
        
        {renderBreakdown()}
        {renderSuggestions()}
      </div>
    </div>
  );
};

export default ATSScoreDisplay;