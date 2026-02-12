import api from "@/lib/api";

export interface Plan {
  key: string;
  name: string;
  price: number;
  price_display: string;
  messages: number;
  resumes: number;
}

export interface PlansResponse {
  plans: Plan[];
  stripe_configured: boolean;
}

export async function getPlans(): Promise<PlansResponse> {
  const { data } = await api.get("/billing/plans");
  return data;
}

export async function createCheckoutSession(
  plan: string
): Promise<{ url: string }> {
  const { data } = await api.post("/billing/create-checkout-session", { plan });
  return data;
}
