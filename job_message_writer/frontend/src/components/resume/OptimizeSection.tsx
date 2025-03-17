import React, { useState } from 'react';
import { toast } from 'react-toastify';

interface OptimizeSectionProps {
  title: string;
  originalContent: string;
  optimizedContent: string;
  onCopy: (content: string) => void;
}

type ViewMode = 'original' | 'optimized' | 'diff';

const OptimizeSection: React.FC<OptimizeSectionProps> = ({
  title,
  originalContent,
  optimizedContent,
  onCopy
}) => {
  const [viewMode, setViewMode] = useState<ViewMode>('optimized');

  const copyToClipboard = () => {
    const contentToCopy = viewMode === 'original' ? originalContent : optimizedContent;
    navigator.clipboard.writeText(contentToCopy);
    toast.success('Copied to clipboard!');
    onCopy(contentToCopy);
  };

  const toggleDiff = (mode: ViewMode) => {
    setViewMode(mode);
  };
  
  // Function to highlight differences between original and optimized text
  const renderDiffView = () => {
    // Simple diff visualization (words added in green, removed in red)
    const originalWords = originalContent.split(/\s+/);
    const optimizedWords = optimizedContent.split(/\s+/);
    
    const addedWords = optimizedWords.filter(word => !originalWords.includes(word));
    const removedWords = originalWords.filter(word => !optimizedWords.includes(word));
    
    return optimizedWords.map((word, index) => {
      if (addedWords.includes(word)) {
        return <span key={index} className="bg-green-200 dark:bg-green-900 px-1 rounded">{word} </span>;
      } else if (removedWords.includes(word)) {
        return <span key={index} className="bg-red-200 dark:bg-red-900 px-1 rounded">{word} </span>;
      } else {
        return <span key={index}>{word} </span>;
      }
    });
  };

  const renderContent = () => {
    switch (viewMode) {
      case 'original':
        return (
          <div className="whitespace-pre-line bg-neutral-50 dark:bg-neutral-900 rounded-lg p-4 text-sm text-neutral-700 dark:text-neutral-300">
            {originalContent}
          </div>
        );
      case 'optimized':
        return (
          <div className="whitespace-pre-line bg-neutral-50 dark:bg-neutral-900 rounded-lg p-4 text-sm text-neutral-700 dark:text-neutral-300">
            {optimizedContent}
          </div>
        );
      case 'diff':
        return (
          <div className="bg-neutral-50 dark:bg-neutral-900 rounded-lg p-4 text-sm text-neutral-700 dark:text-neutral-300">
            {renderDiffView()}
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-soft overflow-hidden mb-6">
      <div className="flex justify-between items-center p-4 border-b border-neutral-200 dark:border-neutral-700">
        <h3 className="text-lg font-medium text-neutral-900 dark:text-neutral-100">{title}</h3>
        <div className="flex space-x-2">
          <button
            onClick={() => copyToClipboard()}
            className="btn btn-outline text-sm py-1 px-3"
          >
            Copy
          </button>
        </div>
      </div>
      
      <div className="p-4">
        <div className="flex border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden mb-4">
          <button
            onClick={() => toggleDiff('original')}
            className={`flex-1 py-2 text-sm font-medium ${
              viewMode === 'original'
                ? 'bg-primary-100 dark:bg-primary-900 text-primary-700 dark:text-primary-300'
                : 'text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700'
            }`}
          >
            Original
          </button>
          <button
            onClick={() => toggleDiff('optimized')}
            className={`flex-1 py-2 text-sm font-medium ${
              viewMode === 'optimized'
                ? 'bg-primary-100 dark:bg-primary-900 text-primary-700 dark:text-primary-300'
                : 'text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700'
            }`}
          >
            Optimized
          </button>
          <button
            onClick={() => toggleDiff('diff')}
            className={`flex-1 py-2 text-sm font-medium ${
              viewMode === 'diff'
                ? 'bg-primary-100 dark:bg-primary-900 text-primary-700 dark:text-primary-300'
                : 'text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700'
            }`}
          >
            View Diff
          </button>
        </div>
        
        {renderContent()}
      </div>
    </div>
  );
};

export default OptimizeSection;