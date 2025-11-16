import { useState, useRef, useEffect } from 'react';
import { toast } from 'react-toastify';
import { AgentMessage, AgentStep, YCStartup, Founder, OutreachEmail, InterviewPrep } from '../types/agent';
import AgentStatusTracker from '../components/agent/AgentStatusTracker';
import YCStartupResults from '../components/agent/YCStartupResults';
import InterviewPrepViewer from '../components/agent/InterviewPrepViewer';

const AgentChat = () => {
  const [messages, setMessages] = useState<AgentMessage[]>([
    {
      id: '1',
      type: 'system',
      content: 'Welcome to Panacea Agent! Tell me your career goal and I\'ll help you find opportunities and connect with the right people.',
      timestamp: new Date(),
    },
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isAgentWorking, setIsAgentWorking] = useState(false);
  const [agentSteps, setAgentSteps] = useState<AgentStep[]>([]);
  const [startups, setStartups] = useState<YCStartup[]>([]);
  const [founders, setFounders] = useState<Founder[]>([]);
  const [outreach, setOutreach] = useState<OutreachEmail[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [interviewPreps, _setInterviewPreps] = useState<InterviewPrep[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [selectedInterviewPrep, _setSelectedInterviewPrep] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSendMessage = async () => {
    if (!inputValue.trim() || isAgentWorking) return;

    const userMessage: AgentMessage = {
      id: Date.now().toString(),
      type: 'user',
      content: inputValue,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setIsAgentWorking(true);

    // Simulate agent response (replace with actual API call)
    simulateAgentWork(inputValue);
  };

  const simulateAgentWork = async (goal: string) => {
    // Add agent acknowledgment
    const ackMessage: AgentMessage = {
      id: Date.now().toString(),
      type: 'agent',
      content: `Got it! I'll help you ${goal.toLowerCase()}. Starting the search process...`,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, ackMessage]);

    // Initialize steps
    const steps: AgentStep[] = [
      {
        id: '1',
        name: 'Finding YC Startups',
        description: 'Searching Y Combinator directory for matching companies...',
        status: 'in_progress',
        startedAt: new Date(),
      },
      {
        id: '2',
        name: 'Extracting Founders',
        description: 'Identifying founders and key contacts...',
        status: 'pending',
      },
      {
        id: '3',
        name: 'Validating Emails',
        description: 'Verifying email addresses and contact information...',
        status: 'pending',
      },
      {
        id: '4',
        name: 'Sending Outreach',
        description: 'Crafting and sending personalized emails...',
        status: 'pending',
      },
    ];

    setAgentSteps(steps);

    // Simulate step progression
    await new Promise((resolve) => setTimeout(resolve, 2000));

    // Step 1 complete
    setAgentSteps((prev) =>
      prev.map((step) =>
        step.id === '1'
          ? { ...step, status: 'completed', completedAt: new Date() }
          : step.id === '2'
          ? { ...step, status: 'in_progress', startedAt: new Date() }
          : step
      )
    );

    // Mock startup data
    const mockStartups: YCStartup[] = [
      {
        id: '1',
        name: 'TechFlow AI',
        batch: 'W24',
        description: 'Building autonomous AI agents for enterprise workflow automation',
        website: 'https://techflow.ai',
        industry: 'B2B SaaS',
        tags: ['AI/ML', 'Enterprise', 'Automation'],
        founded: '2023',
      },
      {
        id: '2',
        name: 'DataStream',
        batch: 'S23',
        description: 'Real-time data pipeline infrastructure for modern applications',
        website: 'https://datastream.io',
        industry: 'Developer Tools',
        tags: ['Infrastructure', 'Data', 'DevTools'],
        founded: '2023',
      },
    ];

    setStartups(mockStartups);

    const statusMessage: AgentMessage = {
      id: Date.now().toString(),
      type: 'agent',
      content: `✅ Found ${mockStartups.length} YC startups matching your criteria!`,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, statusMessage]);

    await new Promise((resolve) => setTimeout(resolve, 2000));

    // Step 2 complete
    setAgentSteps((prev) =>
      prev.map((step) =>
        step.id === '2'
          ? { ...step, status: 'completed', completedAt: new Date() }
          : step.id === '3'
          ? { ...step, status: 'in_progress', startedAt: new Date() }
          : step
      )
    );

    // Mock founders
    const mockFounders: Founder[] = [
      {
        id: '1',
        name: 'Sarah Chen',
        role: 'CEO & Co-Founder',
        linkedinUrl: 'https://linkedin.com/in/sarahchen',
        email: 'sarah@techflow.ai',
        emailConfidence: 'high',
        startupId: '1',
      },
      {
        id: '2',
        name: 'Michael Torres',
        role: 'CTO & Co-Founder',
        linkedinUrl: 'https://linkedin.com/in/michaeltorres',
        email: 'michael@techflow.ai',
        emailConfidence: 'high',
        startupId: '1',
      },
      {
        id: '3',
        name: 'Alex Kumar',
        role: 'CEO & Founder',
        linkedinUrl: 'https://linkedin.com/in/alexkumar',
        email: 'alex@datastream.io',
        emailConfidence: 'medium',
        startupId: '2',
      },
    ];

    setFounders(mockFounders);

    const foundersMessage: AgentMessage = {
      id: Date.now().toString(),
      type: 'agent',
      content: `✅ Extracted ${mockFounders.length} founders and validated their contact information!`,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, foundersMessage]);

    await new Promise((resolve) => setTimeout(resolve, 1500));

    // Step 3 complete
    setAgentSteps((prev) =>
      prev.map((step) =>
        step.id === '3'
          ? { ...step, status: 'completed', completedAt: new Date() }
          : step.id === '4'
          ? { ...step, status: 'in_progress', startedAt: new Date() }
          : step
      )
    );

    // Mock outreach
    const mockOutreach: OutreachEmail[] = mockFounders.map((founder) => ({
      id: `outreach-${founder.id}`,
      founderId: founder.id,
      startupId: founder.startupId,
      subject: `Excited about ${mockStartups.find((s) => s.id === founder.startupId)?.name}`,
      body: 'Personalized email content...',
      status: 'sent',
      sentAt: new Date(),
    }));

    setOutreach(mockOutreach);

    await new Promise((resolve) => setTimeout(resolve, 2000));

    // Step 4 complete
    setAgentSteps((prev) =>
      prev.map((step) =>
        step.id === '4' ? { ...step, status: 'completed', completedAt: new Date() } : step
      )
    );

    const completeMessage: AgentMessage = {
      id: Date.now().toString(),
      type: 'agent',
      content: `🎉 All done! I've sent ${mockOutreach.length} personalized outreach emails. You can track their status below. Good luck with your applications!`,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, completeMessage]);

    setIsAgentWorking(false);
    toast.success('Agent task completed successfully!');
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const examplePrompts = [
    'I want to apply to YC startups as a backend engineer',
    'Find me ML engineering roles at early-stage AI companies',
    'Help me connect with YC founders in fintech',
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-white mb-2 flex items-center">
            <span className="bg-gradient-to-r from-indigo-400 via-purple-400 to-pink-400 text-transparent bg-clip-text">
              Panacea Agent
            </span>
            <span className="ml-3 px-3 py-1 bg-emerald-500/20 text-emerald-400 text-sm rounded-full border border-emerald-500/30">
              Beta
            </span>
          </h1>
          <p className="text-gray-400 text-lg">
            Your AI-powered career assistant for YC outreach and interview prep
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Chat Section */}
          <div className="lg:col-span-2 space-y-6">
            {/* Messages */}
            <div className="bg-gradient-to-br from-slate-900 to-slate-800 rounded-2xl shadow-2xl border border-slate-700 overflow-hidden">
              <div className="h-[500px] overflow-y-auto p-6 space-y-4">
                {messages.map((message) => (
                  <div
                    key={message.id}
                    className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                        message.type === 'user'
                          ? 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white'
                          : message.type === 'system'
                          ? 'bg-slate-700/50 text-gray-300 border border-slate-600'
                          : 'bg-slate-800 text-gray-200 border border-slate-700'
                      }`}
                    >
                      <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                      <p className="text-xs opacity-70 mt-1">
                        {message.timestamp.toLocaleTimeString()}
                      </p>
                    </div>
                  </div>
                ))}

                {isAgentWorking && (
                  <div className="flex justify-start">
                    <div className="bg-slate-800 border border-slate-700 rounded-2xl px-4 py-3">
                      <div className="flex items-center space-x-2">
                        <div className="flex space-x-1">
                          <div className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce"></div>
                          <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                          <div className="w-2 h-2 bg-pink-400 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }}></div>
                        </div>
                        <span className="text-sm text-gray-400">Agent is working...</span>
                      </div>
                    </div>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>

              {/* Input */}
              <div className="border-t border-slate-700 p-4 bg-slate-900/50">
                {messages.length === 1 && (
                  <div className="mb-4">
                    <p className="text-xs text-gray-400 mb-2">Try one of these:</p>
                    <div className="flex flex-wrap gap-2">
                      {examplePrompts.map((prompt, index) => (
                        <button
                          key={index}
                          onClick={() => setInputValue(prompt)}
                          className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-gray-300 text-xs rounded-lg border border-slate-600 transition-colors"
                        >
                          {prompt}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <div className="flex space-x-3">
                  <input
                    ref={inputRef}
                    type="text"
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    onKeyPress={handleKeyPress}
                    placeholder="Tell me your career goal..."
                    disabled={isAgentWorking}
                    className="flex-1 bg-slate-800 border border-slate-600 rounded-xl px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:opacity-50"
                  />
                  <button
                    onClick={handleSendMessage}
                    disabled={!inputValue.trim() || isAgentWorking}
                    className="px-6 py-3 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white rounded-xl font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
                  >
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                    </svg>
                    <span>Send</span>
                  </button>
                </div>
              </div>
            </div>

            {/* Results Section */}
            {startups.length > 0 && (
              <YCStartupResults
                startups={startups}
                founders={founders}
                outreach={outreach}
              />
            )}

            {/* Interview Prep */}
            {selectedInterviewPrep && interviewPreps.length > 0 && (
              <InterviewPrepViewer
                interviewPrep={interviewPreps.find((p) => p.id === selectedInterviewPrep)!}
                startupName={startups.find((s) => s.id === interviewPreps.find((p) => p.id === selectedInterviewPrep)?.startupId)?.name || ''}
              />
            )}
          </div>

          {/* Sidebar - Agent Status */}
          <div className="space-y-6">
            {agentSteps.length > 0 && (
              <AgentStatusTracker steps={agentSteps} />
            )}

            {/* Stats Card */}
            <div className="bg-gradient-to-br from-slate-900 to-slate-800 rounded-2xl p-6 shadow-2xl border border-slate-700">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center">
                <svg className="w-5 h-5 mr-2 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
                Current Stats
              </h3>

              <div className="space-y-3">
                <div className="bg-slate-800/50 rounded-lg p-3 border border-slate-700">
                  <div className="text-sm text-gray-400">Startups Found</div>
                  <div className="text-2xl font-bold text-white mt-1">{startups.length}</div>
                </div>

                <div className="bg-slate-800/50 rounded-lg p-3 border border-slate-700">
                  <div className="text-sm text-gray-400">Founders Contacted</div>
                  <div className="text-2xl font-bold text-white mt-1">{founders.length}</div>
                </div>

                <div className="bg-slate-800/50 rounded-lg p-3 border border-slate-700">
                  <div className="text-sm text-gray-400">Emails Sent</div>
                  <div className="text-2xl font-bold text-white mt-1">
                    {outreach.filter((o) => o.status === 'sent').length}
                  </div>
                </div>

                <div className="bg-slate-800/50 rounded-lg p-3 border border-slate-700">
                  <div className="text-sm text-gray-400">Replies</div>
                  <div className="text-2xl font-bold text-emerald-400 mt-1">
                    {outreach.filter((o) => o.status === 'replied').length}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AgentChat;
