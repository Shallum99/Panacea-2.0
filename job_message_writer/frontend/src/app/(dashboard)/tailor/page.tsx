"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function TailorPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/generate");
  }, [router]);
  return null;
}
