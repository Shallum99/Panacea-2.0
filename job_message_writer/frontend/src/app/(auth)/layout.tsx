import { MessageSquareText, FileText, Search } from "lucide-react";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen flex">
      {/* Left brand panel - hidden on mobile */}
      <div className="hidden lg:flex lg:w-[60%] relative overflow-hidden bg-[#07070a] flex-col justify-between p-12">
        {/* Gradient mesh background */}
        <div
          className="absolute inset-0 opacity-30"
          style={{
            background:
              "radial-gradient(ellipse at 20% 50%, rgba(59,130,246,0.15) 0%, transparent 50%), radial-gradient(ellipse at 80% 20%, rgba(139,92,246,0.12) 0%, transparent 50%), radial-gradient(ellipse at 50% 80%, rgba(59,130,246,0.08) 0%, transparent 50%)",
          }}
        />
        {/* Subtle grid pattern */}
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage:
              "linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)",
            backgroundSize: "64px 64px",
          }}
        />

        {/* Top: Brand */}
        <div className="relative z-10">
          <h1 className="text-gradient text-5xl font-bold tracking-tight">
            Panacea
          </h1>
          <p className="mt-3 text-lg text-[#a1a1aa] max-w-md leading-relaxed">
            Your AI-powered job application assistant
          </p>
        </div>

        {/* Middle: Feature bullets */}
        <div className="relative z-10 space-y-8">
          <FeatureBullet
            icon={<MessageSquareText className="w-5 h-5" />}
            title="AI Messages"
            description="Generate tailored cover letters and outreach messages in seconds"
          />
          <FeatureBullet
            icon={<FileText className="w-5 h-5" />}
            title="Resume Optimization"
            description="Automatically tailor your resume to match any job description"
          />
          <FeatureBullet
            icon={<Search className="w-5 h-5" />}
            title="Smart Job Search"
            description="Find and track opportunities that match your skills and goals"
          />
        </div>

        {/* Bottom: subtle footer */}
        <div className="relative z-10">
          <p className="text-xs text-[#52525b]">
            &copy; {new Date().getFullYear()} Panacea. All rights reserved.
          </p>
        </div>
      </div>

      {/* Right form panel */}
      <div className="w-full lg:w-[40%] flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">{children}</div>
      </div>
    </div>
  );
}

function FeatureBullet({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="flex items-start gap-4">
      <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-[#ffffff08] border border-[#ffffff0a] flex items-center justify-center text-[#a1a1aa]">
        {icon}
      </div>
      <div>
        <h3 className="text-sm font-semibold text-[#fafafa]">{title}</h3>
        <p className="text-sm text-[#71717a] mt-0.5 leading-relaxed">
          {description}
        </p>
      </div>
    </div>
  );
}
