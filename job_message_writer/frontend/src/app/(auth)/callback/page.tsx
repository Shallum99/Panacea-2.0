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

    // Detect if this is an OAuth redirect (URL has code= param from PKCE flow)
    const params = new URLSearchParams(window.location.search);
    const isOAuthRedirect = params.has("code");

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
        } catch (err) {
          console.warn("Failed to save Gmail token:", err);
        }
      }

      router.push("/dashboard");
    }

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (event, session) => {
      if (!session) return;

      if (isOAuthRedirect) {
        // OAuth flow: ONLY accept SIGNED_IN — it has the fresh session
        // with provider_refresh_token. INITIAL_SESSION fires first with
        // the stale cached session and must be ignored.
        if (event === "SIGNED_IN") {
          handleSession(session);
        }
      } else {
        // Direct navigation: accept any session
        if (event === "SIGNED_IN" || event === "INITIAL_SESSION") {
          handleSession(session);
        }
      }
    });

    // Safety net: redirect after 5s regardless
    const timeout = setTimeout(async () => {
      if (!handled.current) {
        const {
          data: { session },
        } = await supabase.auth.getSession();
        if (session) {
          handleSession(session);
        } else {
          router.push("/login");
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
