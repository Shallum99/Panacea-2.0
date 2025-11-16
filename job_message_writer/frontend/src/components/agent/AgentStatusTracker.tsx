import { AgentStep } from '../../types/agent';

interface AgentStatusTrackerProps {
  steps: AgentStep[];
}

const AgentStatusTracker = ({ steps }: AgentStatusTrackerProps) => {
  const getStepIcon = (status: AgentStep['status']) => {
    switch (status) {
      case 'completed':
        return (
          <div className="flex items-center justify-center w-8 h-8 rounded-full bg-green-500">
            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
        );
      case 'in_progress':
        return (
          <div className="flex items-center justify-center w-8 h-8 rounded-full bg-blue-500">
            <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
          </div>
        );
      case 'error':
        return (
          <div className="flex items-center justify-center w-8 h-8 rounded-full bg-red-500">
            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>
        );
      default:
        return (
          <div className="flex items-center justify-center w-8 h-8 rounded-full bg-gray-300 dark:bg-gray-600">
            <div className="w-3 h-3 rounded-full bg-gray-400 dark:bg-gray-500"></div>
          </div>
        );
    }
  };

  const getStepColor = (status: AgentStep['status']) => {
    switch (status) {
      case 'completed':
        return 'text-green-600 dark:text-green-400';
      case 'in_progress':
        return 'text-blue-600 dark:text-blue-400';
      case 'error':
        return 'text-red-600 dark:text-red-400';
      default:
        return 'text-gray-500 dark:text-gray-400';
    }
  };

  return (
    <div className="bg-gradient-to-br from-slate-900 to-slate-800 rounded-2xl p-6 shadow-2xl border border-slate-700">
      <h3 className="text-lg font-semibold text-white mb-6 flex items-center">
        <svg className="w-5 h-5 mr-2 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
        Agent Progress
      </h3>

      <div className="space-y-4">
        {steps.map((step, index) => (
          <div key={step.id} className="flex items-start space-x-4">
            {/* Step Icon */}
            <div className="flex-shrink-0 relative">
              {getStepIcon(step.status)}
              {index < steps.length - 1 && (
                <div className="absolute top-8 left-4 w-0.5 h-8 bg-gray-600"></div>
              )}
            </div>

            {/* Step Content */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <h4 className={`text-sm font-medium ${getStepColor(step.status)}`}>
                  {step.name}
                </h4>
                {step.status === 'in_progress' && (
                  <span className="text-xs text-blue-400 animate-pulse">
                    Processing...
                  </span>
                )}
              </div>

              <p className="mt-1 text-sm text-gray-400">
                {step.description}
              </p>

              {step.error && (
                <div className="mt-2 p-2 bg-red-900/30 border border-red-700 rounded-lg">
                  <p className="text-xs text-red-400">{step.error}</p>
                </div>
              )}

              {step.completedAt && (
                <p className="mt-1 text-xs text-gray-500">
                  Completed at {new Date(step.completedAt).toLocaleTimeString()}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default AgentStatusTracker;
