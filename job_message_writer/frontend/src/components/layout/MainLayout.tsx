import { useContext } from 'react';
import { Outlet, Link, useNavigate } from 'react-router-dom';
import { AuthContext } from '../../context/AuthContext';

const MainLayout = () => {
  const { isAuthenticated, user, logout } = useContext(AuthContext);
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header/Navbar */}
      <header className="bg-white dark:bg-neutral-800 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16 items-center">
            {/* Logo */}
            <div className="flex-shrink-0">
              <Link to="/" className="flex items-center">
                <span className="text-primary-600 dark:text-primary-400 font-bold text-xl">JobMessageWriter</span>
              </Link>
            </div>
            
            {/* Navigation */}
            <nav className="hidden md:flex space-x-10">
              <Link to="/" className="text-neutral-700 dark:text-neutral-300 hover:text-primary-600 dark:hover:text-primary-400">
                Home
              </Link>
              
              {isAuthenticated && (
                <>
                  <Link to="/dashboard" className="text-neutral-700 dark:text-neutral-300 hover:text-primary-600 dark:hover:text-primary-400">
                    Dashboard
                  </Link>
                  <Link to="/message-generator" className="text-neutral-700 dark:text-neutral-300 hover:text-primary-600 dark:hover:text-primary-400">
                    Generate Message
                  </Link>
                  <Link to="/resume-tailor" className="text-neutral-700 dark:text-neutral-300 hover:text-primary-600 dark:hover:text-primary-400">
                    Tailor Resume                
                  </Link>
                </>
              )}
            </nav>
            
            {/* Right side buttons */}
            <div className="flex items-center">
              {isAuthenticated ? (
                <div className="flex items-center space-x-4">
                  <span className="text-neutral-700 dark:text-neutral-300">{user?.email}</span>
                  <button 
                    onClick={logout}
                    className="btn btn-outline"
                  >
                    Log out
                  </button>
                </div>
              ) : (
                <div className="flex items-center space-x-4">
                  <button 
                    onClick={() => navigate('/login')}
                    className="btn btn-outline"
                  >
                    Log in
                  </button>
                  <button 
                    onClick={() => navigate('/signup')}
                    className="btn btn-primary"
                  >
                    Sign up
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </header>
      
      {/* Main content */}
      <main className="flex-grow">
        <Outlet />
      </main>
      
      {/* Footer */}
      <footer className="bg-white dark:bg-neutral-800 shadow-sm mt-auto">
        <div className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
          <p className="text-center text-neutral-600 dark:text-neutral-400">
            © {new Date().getFullYear()} JobMessageWriter. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
};

export default MainLayout;