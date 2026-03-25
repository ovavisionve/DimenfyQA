"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/auth";
import { Sidebar } from "@/components/layout/sidebar";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
    } else {
      setReady(true);
    }
  }, [router]);

  if (!ready) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-300 border-t-amber-500" />
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-zinc-50">
      <Sidebar />
      <main className="flex-1 min-w-0 overflow-y-auto">
        <div className="p-6">{children}</div>
      </main>
    </div>
  );
}
