import Link from "next/link";

export default function Home() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4">
      <div className="max-w-2xl text-center space-y-6">
        <h1 className="text-5xl font-bold tracking-tight">Panacea</h1>
        <p className="text-lg text-muted-foreground">
          AI-powered job applications. Generate messages, tailor resumes, and
          auto-apply — all from one place.
        </p>
        <div className="flex items-center justify-center gap-4 pt-4">
          <Link
            href="/signup"
            className="px-6 py-2.5 bg-accent text-accent-foreground text-sm font-medium rounded-lg hover:opacity-90 transition-opacity"
          >
            Get Started
          </Link>
          <Link
            href="/login"
            className="px-6 py-2.5 text-sm font-medium text-muted-foreground border border-border rounded-lg hover:text-foreground hover:border-muted-foreground transition-colors"
          >
            Sign In
          </Link>
        </div>
      </div>
    </div>
  );
}
