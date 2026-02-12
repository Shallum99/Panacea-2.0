import api from "@/lib/api";

export interface Profile {
  full_name: string | null;
  email: string;
  phone: string | null;
  linkedin_url: string | null;
  portfolio_url: string | null;
  professional_summary: string | null;
  master_skills: string[] | null;
  target_roles: string[] | null;
  target_industries: string[] | null;
  target_locations: string[] | null;
  work_arrangement: string | null;
  salary_range_min: number | null;
  salary_range_max: number | null;
  tone_formality: string;
  tone_confidence: string;
  tone_verbosity: string;
}

export interface WritingSample {
  id: number;
  title: string | null;
  content: string;
  sample_type: string | null;
  created_at: string | null;
}

export async function getProfile(): Promise<Profile> {
  const { data } = await api.get("/profile/");
  return data;
}

export async function updateProfile(
  update: Partial<Profile>
): Promise<Profile> {
  const { data } = await api.patch("/profile/", update);
  return data;
}

export async function getWritingSamples(): Promise<WritingSample[]> {
  const { data } = await api.get("/profile/writing-samples");
  return data;
}

export async function createWritingSample(body: {
  title?: string;
  content: string;
  sample_type?: string;
}): Promise<WritingSample> {
  const { data } = await api.post("/profile/writing-samples", body);
  return data;
}

export async function deleteWritingSample(id: number): Promise<void> {
  await api.delete(`/profile/writing-samples/${id}`);
}
