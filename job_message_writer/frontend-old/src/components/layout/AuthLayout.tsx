import { Outlet, Link } from 'react-router-dom';

const AuthLayout = () => {
  return (
    <div className="min-h-screen flex flex-col bg-neutral-50 dark:bg-neutral-900">
      {/* Header with logo only */}
      <header className="py-6">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <Link to="/" className="flex items-center justify-center">
            <span className="text-primary-600 dark:text-primary-400 font-bold text-2xl">JobMessageWriter</span>
          </Link>
        </div>
      </header>
      
      {/* Main content */}
      <main className="flex-grow flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-md w-full">
          <Outlet />
        </div>
      </main>
      
      {/* Footer */}
      <footer className="py-6">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <p className="text-center text-neutral-600 dark:text-neutral-400">
            © {new Date().getFullYear()} JobMessageWriter. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
};

export default AuthLayout;