"use client";

import { useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";
import api from "@/lib/api";

export default function CallbackPage() {
  const router = useRouter();

  useEffect(() => {
    const supabase = createClient();

    supabase.auth.onAuthStateChange(async (event, session) => {
      if (event === "SIGNED_IN" && session) {
        // Capture Google refresh token (only available right after OAuth)
        const refreshToken = session.provider_refresh_token;
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
    });
  }, [router]);

  return (
    <div className="flex items-center justify-center min-h-[50vh]">
      <p className="text-sm text-muted-foreground">Authenticating...</p>
    </div>
  );
}
