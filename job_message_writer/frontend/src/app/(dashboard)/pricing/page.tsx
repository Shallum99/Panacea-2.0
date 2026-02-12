"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import api from "@/lib/api";
import { getPlans, createCheckoutSession, type Plan } from "@/lib/api/billing";

const PLAN_FEATURES: Record<string, string[]> = {
  pro: [
    "50 AI message generations",
    "50 resume tailorings",
    "PDF format preservation",
    "ATS score optimization",
    "Email sending",
  ],
  business: [
    "150 AI message generations",
    "150 resume tailorings",
    "Everything in Pro",
    "Priority support",
  ],
  enterprise: [
    "1,000 AI message generations",
    "1,000 resume tailorings",
    "Everything in Business",
    "Priority support",
    "Early access to new features",
  ],
};

export default function PricingPage() {
  const searchParams = useSearchParams();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [stripeConfigured, setStripeConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [purchasing, setPurchasing] = useState<string | null>(null);
  const [usage, setUsage] = useState<{ tier: string; message_generation: { used: number; limit: number | null }; resume_tailor: { used: number; limit: number | null } } | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [plansData, usageData] = await Promise.all([
          getPlans(),
          api.get("/users/usage").then((r) => r.data),
        ]);
        setPlans(plansData.plans);
        setStripeConfigured(plansData.stripe_configured);
        setUsage(usageData);
      } catch {
        toast.error("Failed to load plans");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  useEffect(() => {
    if (searchParams.get("success") === "true") {
      const plan = searchParams.get("plan");
      toast.success(`Successfully upgraded to ${plan ? plan.charAt(0).toUpperCase() + plan.slice(1) : "new plan"}!`);
    }
    if (searchParams.get("canceled") === "true") {
      toast.error("Payment was canceled");
    }
  }, [searchParams]);

  async function handleBuy(planKey: string) {
    setPurchasing(planKey);
    try {
      const { url } = await createCheckoutSession(planKey);
      window.location.href = url;
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Failed to start checkout");
      setPurchasing(null);
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <div><h1 className="text-2xl font-bold tracking-tight">Pricing</h1></div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
            <div key={i} className="border border-border rounded-xl p-6 animate-pulse space-y-4">
              <div className="h-6 bg-muted rounded w-1/3" />
              <div className="h-10 bg-muted rounded w-1/2" />
              <div className="space-y-2">
                <div className="h-3 bg-muted rounded w-full" />
                <div className="h-3 bg-muted rounded w-5/6" />
                <div className="h-3 bg-muted rounded w-4/6" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  const isCurrentTier = (planKey: string) => usage?.tier === planKey;
  const isFree = usage?.tier === "free";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Pricing</h1>
        <p className="text-sm text-muted-foreground mt-1">
          One-time payment. No subscriptions. Upgrade whenever you need more.
        </p>
      </div>

      {/* Current plan banner */}
      {usage && (
        <div className="border border-border rounded-lg px-4 py-3 flex items-center justify-between">
          <div>
            <span className="text-sm font-medium">Current plan: </span>
            <span className="text-sm font-bold text-accent capitalize">{usage.tier}</span>
          </div>
          {usage.message_generation.limit !== null && (
            <div className="flex items-center gap-4 text-xs text-muted-foreground">
              <span>Messages: <span className="font-mono">{usage.message_generation.used}/{usage.message_generation.limit}</span></span>
              <span>Resumes: <span className="font-mono">{usage.resume_tailor.used}/{usage.resume_tailor.limit}</span></span>
            </div>
          )}
          {usage.message_generation.limit === null && (
            <span className="text-xs text-muted-foreground">Unlimited</span>
          )}
        </div>
      )}

      {/* Plan cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {plans.map((plan) => {
          const features = PLAN_FEATURES[plan.key] || [];
          const current = isCurrentTier(plan.key);
          const recommended = plan.key === "business";

          return (
            <div
              key={plan.key}
              className={`relative border rounded-xl p-6 flex flex-col transition-colors ${
                recommended
                  ? "border-accent bg-accent/5"
                  : current
                  ? "border-accent/50"
                  : "border-border hover:border-muted-foreground/30"
              }`}
            >
              {recommended && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-accent text-accent-foreground text-[10px] font-bold uppercase tracking-wider px-3 py-1 rounded-full">
                  Most Popular
                </span>
              )}

              <div className="mb-4">
                <h3 className="text-lg font-bold">{plan.name}</h3>
                <div className="mt-2">
                  <span className="text-3xl font-bold">{plan.price_display}</span>
                  <span className="text-sm text-muted-foreground ml-1">one-time</span>
                </div>
              </div>

              <ul className="space-y-2.5 flex-1 mb-6">
                {features.map((f, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <svg className="w-4 h-4 mt-0.5 text-accent shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    <span className="text-muted-foreground">{f}</span>
                  </li>
                ))}
              </ul>

              {current ? (
                <div className="h-10 flex items-center justify-center text-sm font-medium text-accent border border-accent/30 rounded-lg">
                  Current Plan
                </div>
              ) : stripeConfigured ? (
                <button
                  onClick={() => handleBuy(plan.key)}
                  disabled={purchasing !== null}
                  className={`h-10 text-sm font-medium rounded-lg transition-opacity disabled:opacity-40 disabled:cursor-not-allowed ${
                    recommended
                      ? "bg-accent text-accent-foreground hover:opacity-90"
                      : "border border-accent text-accent hover:bg-accent/10"
                  }`}
                >
                  {purchasing === plan.key ? "Redirecting..." : `Buy ${plan.name}`}
                </button>
              ) : (
                <div className="h-10 flex items-center justify-center text-sm text-muted-foreground border border-border rounded-lg">
                  Coming Soon
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Free tier info */}
      {isFree && (
        <div className="text-center text-xs text-muted-foreground py-4">
          Free tier includes 5 message generations and 5 resume tailorings to get started.
        </div>
      )}
    </div>
  );
}
