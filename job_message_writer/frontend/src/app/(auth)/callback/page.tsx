"use client";

import { useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";
import api from "@/lib/api";

export default function CallbackPage() {
  const router = useRouter();

  useEffect(() => {
    const supabase = createClient();

    async function saveTokenAndRedirect(session: any) {
      const refreshToken = session?.provider_refresh_token;
      if (refreshToken) {
        try {
          await api.post("/users/save-gmail-token", {
            refresh_token: refreshToken,
          });
        } catch (err) {
          console.warn("Failed to save Gmail token:", err);
        }
      }
      router.push("/dashboard");
    }

    // Check if session already exists (event may have fired before mount)
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        saveTokenAndRedirect(session);
      }
    });

    // Also listen for the event in case it hasn't fired yet
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (event, session) => {
        if (event === "SIGNED_IN" && session) {
          saveTokenAndRedirect(session);
        }
      }
    );

    return () => subscription.unsubscribe();
  }, [router]);

  return (
    <div className="flex items-center justify-center min-h-[50vh]">
      <p className="text-sm text-muted-foreground">Authenticating...</p>
    </div>
  );
}
