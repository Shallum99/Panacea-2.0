"use client";

import { useEffect, useRef } from "react";
import { createClient } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";
import api from "@/lib/api";

export default function CallbackPage() {
  const router = useRouter();
  const handled = useRef(false);

  useEffect(() => {
    const supabase = createClient();

    async function handleSession(session: any) {
      if (handled.current) return;
      handled.current = true;

      // Save Gmail refresh token if present
      const providerRefreshToken = session?.provider_refresh_token;
      if (providerRefreshToken) {
        try {
          await api.post("/users/save-gmail-token", {
            refresh_token: providerRefreshToken,
          });
          console.log("Gmail refresh token saved");
        } catch (err) {
          console.warn("Failed to save Gmail token:", err);
        }
      }

      router.push("/dashboard");
    }

    // Listen for auth state change — this is the ONLY reliable way to get
    // provider_refresh_token, since getSession() returns the cached session
    // without it.
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (event, session) => {
      if (session && (event === "SIGNED_IN" || event === "INITIAL_SESSION")) {
        handleSession(session);
      }
    });

    // Safety net: if no auth event fires within 5s, check session and redirect
    const timeout = setTimeout(async () => {
      if (!handled.current) {
        const {
          data: { session },
        } = await supabase.auth.getSession();
        if (session) {
          handleSession(session);
        }
      }
    }, 5000);

    return () => {
      subscription.unsubscribe();
      clearTimeout(timeout);
    };
  }, [router]);

  return (
    <div className="flex items-center justify-center min-h-[50vh]">
      <p className="text-sm text-muted-foreground">Authenticating...</p>
    </div>
  );
}
