import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { useDropzone } from 'react-dropzone';
import { toast } from 'react-toastify';
import { uploadResume } from '../api/resume';

interface FormData {
  title: string;
  makeActive: boolean;
}

const ResumeUpload = () => {
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const navigate = useNavigate();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormData>({
    defaultValues: {
      title: 'My Resume',
      makeActive: true,
    },
  });

  const { getRootProps, getInputProps, isDragActive, acceptedFiles } = useDropzone({
    accept: {
      'application/pdf': ['.pdf'],
    },
    maxFiles: 1,
    onDrop: (acceptedFiles) => {
      const file = acceptedFiles[0];
      if (file) {
        setFile(file);
      }
    },
  });

  // Simulate upload progress
  const simulateProgress = () => {
    setUploadProgress(0);
    const interval = setInterval(() => {
      setUploadProgress((prev) => {
        const newProgress = prev + Math.random() * 10;
        if (newProgress >= 90) {
          clearInterval(interval);
          return 90;
        }
        return newProgress;
      });
    }, 300);
    return interval;
  };

  const onSubmit = async (data: FormData) => {
    if (!file) {
      toast.error('Please upload a resume');
      return;
    }

    setIsUploading(true);
    const progressInterval = simulateProgress();

    try {
      const response = await uploadResume(file, data.title, data.makeActive);
      clearInterval(progressInterval);
      setUploadProgress(100);
      toast.success('Resume uploaded successfully!');
      
      // Give some time for the 100% progress to be visible
      setTimeout(() => {
        navigate('/dashboard');
      }, 1000);
    } catch (error) {
      console.error('Upload error:', error);
      clearInterval(progressInterval);
      setUploadProgress(0);
      toast.error('Failed to upload resume. Please try again.');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-bold text-neutral-900 dark:text-neutral-100">Upload Your Resume</h1>
        <p className="mt-2 text-neutral-600 dark:text-neutral-400">
          We'll analyze your resume to personalize your application messages
        </p>
      </div>

      <div className="card mb-6">
        <form onSubmit={handleSubmit(onSubmit)}>
          <div className="mb-6">
            <label htmlFor="title" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Profile Title
            </label>
            <input
              id="title"
              type="text"
              className="input w-full"
              placeholder="e.g., Software Engineer Resume"
              {...register('title', { required: 'Title is required' })}
            />
            {errors.title && (
              <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.title.message}</p>
            )}
          </div>

          <div className="mb-6">
            <div 
              {...getRootProps()} 
              className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
                isDragActive 
                  ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20' 
                  : 'border-neutral-300 dark:border-neutral-700 hover:border-primary-500 dark:hover:border-primary-500'
              }`}
            >
              <input {...getInputProps()} />
              {file ? (
                <div className="flex flex-col items-center">
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-10 w-10 text-primary-500 mb-3" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clipRule="evenodd" />
                  </svg>
                  <p className="text-sm font-medium text-neutral-900 dark:text-neutral-100">{file.name}</p>
                  <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">{(file.size / (1024 * 1024)).toFixed(2)} MB</p>
                  <button
                    type="button"
                    className="mt-2 text-xs text-primary-600 dark:text-primary-400 hover:underline"
                    onClick={(e) => {
                      e.stopPropagation();
                      setFile(null);
                    }}
                  >
                    Remove file
                  </button>
                </div>
              ) : (
                <div>
                  <svg xmlns="http://www.w3.org/2000/svg" className="mx-auto h-12 w-12 text-neutral-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                  <p className="mt-2 text-sm font-medium text-neutral-900 dark:text-neutral-100">
                    {isDragActive ? 'Drop the file here' : 'Drag & drop your resume, or click to select'}
                  </p>
                  <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
                    PDF files only (max. 10MB)
                  </p>
                </div>
              )}
            </div>
          </div>

          <div className="mb-6 flex items-center">
            <input
              id="makeActive"
              type="checkbox"
              className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-neutral-300 rounded"
              {...register('makeActive')}
            />
            <label htmlFor="makeActive" className="ml-2 block text-sm text-neutral-700 dark:text-neutral-300">
              Set as active profile
            </label>
          </div>

          {isUploading && (
            <div className="mb-4">
              <div className="w-full bg-neutral-200 dark:bg-neutral-700 rounded-full h-2.5">
                <div
                  className="bg-primary-600 h-2.5 rounded-full transition-all duration-300"
                  style={{ width: `${uploadProgress}%` }}
                ></div>
              </div>
              <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1 text-right">
                {uploadProgress < 100 ? 'Uploading and analyzing...' : 'Analysis complete!'}
              </p>
            </div>
          )}

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={isUploading || !file}
              className="btn btn-primary"
            >
              {isUploading ? 'Processing...' : 'Upload Resume'}
            </button>
          </div>
        </form>
      </div>

      <div className="card">
        <h2 className="text-lg font-medium text-neutral-900 dark:text-neutral-100 mb-4">What happens next?</h2>
        <ol className="space-y-4">
          <li className="flex">
            <div className="flex-shrink-0">
              <div className="flex items-center justify-center h-8 w-8 rounded-full bg-primary-100 dark:bg-primary-900 text-primary-600 dark:text-primary-300">
                1
              </div>
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-neutral-900 dark:text-neutral-100">Resume Analysis</p>
              <p className="text-sm text-neutral-600 dark:text-neutral-400">
                Our AI analyzes your resume to extract key information about your skills and experience.
              </p>
            </div>
          </li>
          <li className="flex">
            <div className="flex-shrink-0">
              <div className="flex items-center justify-center h-8 w-8 rounded-full bg-primary-100 dark:bg-primary-900 text-primary-600 dark:text-primary-300">
                2
              </div>
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-neutral-900 dark:text-neutral-100">Dashboard Access</p>
              <p className="text-sm text-neutral-600 dark:text-neutral-400">
                Once uploaded, you'll be taken to your dashboard where you can manage your resume profiles.
              </p>
            </div>
          </li>
          <li className="flex">
            <div className="flex-shrink-0">
              <div className="flex items-center justify-center h-8 w-8 rounded-full bg-primary-100 dark:bg-primary-900 text-primary-600 dark:text-primary-300">
                3
              </div>
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-neutral-900 dark:text-neutral-100">Generate Messages</p>
              <p className="text-sm text-neutral-600 dark:text-neutral-400">
                Start generating personalized messages for job applications based on your resume.
              </p>
            </div>
          </li>
        </ol>
      </div>
    </div>
  );
};

export default ResumeUpload;