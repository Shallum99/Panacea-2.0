Panacea - AI Job Assistant

A full-stack web application that helps users generate personalized messages for job applications based on their resume and job descriptions.

## 🌟 Features

- **Resume Analysis**: Upload your resume once and have it automatically analyzed to extract key information
- **Job Description Analysis**: Extract company information, technologies, and requirements from job descriptions
- **Personalized Messages**: Generate custom messages for different platforms:
  - LinkedIn Connection Requests (200 characters)
  - LinkedIn Messages (300 characters)
  - LinkedIn InMail (2000 characters)
  - Short Emails (1000 characters)
  - Detailed Emails (3000 characters)
  - Y Combinator Applications (500 characters)
- **Multiple Resume Profiles**: Manage different resume profiles for different job types
- **Dashboard**: View all your resumes and statistics in a clean interface
- **User Authentication**: Secure login and registration system

## 🔧 Tech Stack

### Backend
- **FastAPI**: Modern, fast web framework for building APIs with Python
- **SQLAlchemy**: SQL toolkit and Object-Relational Mapping (ORM)
- **PostgreSQL**: Relational database for data storage
- **Alembic**: Database migration tool
- **Claude AI**: Integration with Anthropic's Claude API for AI-powered analysis and generation
- **JWT**: Authentication with JSON Web Tokens
- **PDF Processing**: Extract text from PDF resumes

### Frontend
- **React**: JavaScript library for building user interfaces
- **TypeScript**: Static typing for improved development experience
- **React Router**: For client-side routing
- **Axios**: HTTP client for API requests
- **React Hook Form**: Form validation and management
- **React Dropzone**: File upload functionality
- **React Toastify**: Notification system
- **Tailwind CSS**: Utility-first CSS framework for styling

### DevOps
- **Docker**: Container-based deployment with Docker Compose
- **Nginx**: Web server for the frontend
- **Environment Variables**: Configuration via .env files
- **Continuous Deployment**: Ready for deployment on platforms like Render

## 📋 Getting Started

### Prerequisites
- Docker and Docker Compose
- Node.js 18+ (for local development)
- Python 3.10+ (for local development)
- Anthropic API Key (for Claude AI integration)

### Environment Setup

Create a `.env` file in the root directory with the following variables:

```
SECRET_KEY=your_secret_key
ANTHROPIC_API_KEY=your_anthropic_api_key
ANTHROPIC_MODEL=claude-3-sonnet-20240229
```

### Running with Docker

1. Clone the repository:
```bash
git clone https://github.com/your-username/job-message-writer.git
cd job-message-writer
```

2. Build and start the containers:
```bash
docker-compose up -d
```

This will start:
- Frontend: http://localhost
- Backend: http://localhost:8000
- PostgreSQL database

### Running Locally for Development

#### Backend

1. Navigate to the backend directory:
```bash
cd job_message_writer/backend
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run database migrations:
```bash
alembic upgrade head
```

5. Start the backend server:
```bash
uvicorn app.main:app --reload
```

#### Frontend

1. Navigate to the frontend directory:
```bash
cd job_message_writer/frontend
```

2. Install dependencies:
```bash
npm install
```

3. Start the development server:
```bash
npm run dev
```

## 🗄️ Project Structure

```
job_message_writer/
├── backend/
│   ├── alembic/                # Database migration scripts
│   ├── app/
│   │   ├── api/
│   │   │   ├── endpoints/      # API route handlers
│   │   │   └── api.py          # API router setup
│   │   ├── core/               # Core settings and configuration
│   │   ├── db/                 # Database models and setup
│   │   ├── llm/                # AI integration modules
│   │   ├── schemas/            # Pydantic schemas for validation
│   │   ├── utils/              # Utility functions
│   │   └── main.py             # Application entry point
│   ├── requirements.txt        # Python dependencies
│   └── Dockerfile              # Backend Docker configuration
├── frontend/
│   ├── public/                 # Public assets
│   ├── src/
│   │   ├── api/                # API client functions
│   │   ├── components/         # React components
│   │   │   └── layout/         # Layout components
│   │   ├── context/            # React context providers
│   │   ├── pages/              # Page components
│   │   ├── App.tsx             # Main application component
│   │   └── main.tsx            # Entry point
│   ├── package.json            # JavaScript dependencies
│   └── Dockerfile              # Frontend Docker configuration
├── docker-compose.yml          # Docker Compose configuration
└── README.md                   # Project documentation
```

## 🔐 Authentication

The application uses JWT (JSON Web Tokens) for authentication. Tokens are stored in local storage and attached to API requests through an Axios interceptor.

## 🗃️ Database Schema

- **Users**: User accounts and authentication data
- **Resumes**: Resume profiles with extracted information
- **JobDescriptions**: Stored job descriptions with company analysis
- **Messages**: Generated application messages

## 🚀 Deployment

### Render Deployment

This application is configured for easy deployment on Render:

1. Create a new Web Service for the backend
2. Set the build command to `pip install -r requirements.txt`
3. Set the start command to `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables from the `.env` file
5. Create a new Static Site for the frontend
6. Set the build command to `npm install && npm run build`
7. Set the publish directory to `dist`
8. Add the environment variable `VITE_API_BASE_URL` pointing to your backend URL

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 👨‍💻 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📧 Contact

Your Name - Shallum Israel Maryapanor
