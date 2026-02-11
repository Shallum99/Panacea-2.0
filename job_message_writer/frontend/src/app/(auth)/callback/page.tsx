"use client";

import { useEffect, useRef } from "react";
import { createClient } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";

export default function CallbackPage() {
  const router = useRouter();
  const handled = useRef(false);

  useEffect(() => {
    const supabase = createClient();

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      if (!session || handled.current) return;

      if (event === "SIGNED_IN" || event === "INITIAL_SESSION") {
        handled.current = true;
        router.push("/dashboard");
      }
    });

    // Safety net
    const timeout = setTimeout(async () => {
      if (!handled.current) {
        const {
          data: { session },
        } = await supabase.auth.getSession();
        handled.current = true;
        router.push(session ? "/dashboard" : "/login");
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
