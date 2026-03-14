"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface Analysis {
  id: number;
  repo_id: string;
  repo_path: string;
  commit_sha: string | null;
  run_at: string;
}

export default function HomePage() {
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch(`${API_BASE}/analyses`);
        if (!res.ok) throw new Error(`Failed to load analyses: ${res.status}`);
        const data = await res.json();
        if (cancelled) return;
        setAnalyses(Array.isArray(data) ? data : []);
        const list = Array.isArray(data) ? data : [];
        // Always redirect: to first analysis if available, else to /analyses/1 (dashboard).
        const targetId = list.length > 0 ? list[0].id : 1;
        router.replace(`/analyses/${targetId}`);
      } catch (e: any) {
        if (!cancelled) setError(e.message ?? String(e));
        if (!cancelled) router.replace("/analyses/1");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [router]);

  return (
    <div className="relative grid min-h-screen place-items-center overflow-hidden px-6">
      <div className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(circle_at_12%_-8%,rgba(239,68,68,0.3),transparent_45%),radial-gradient(circle_at_88%_0%,rgba(153,27,27,0.35),transparent_42%),linear-gradient(to_bottom,#0a0a0b,#18181b)]" />
      <div className="w-full max-w-xl rounded-3xl border border-red-900/70 bg-gradient-to-br from-zinc-900/90 to-zinc-900/60 p-8 text-center shadow-[0_18px_45px_rgba(0,0,0,0.45)] backdrop-blur">
        <div className="mx-auto mb-4 flex w-fit items-center gap-2 rounded-full border border-red-900/70 bg-zinc-950/80 px-4 py-1">
          <span className="h-2.5 w-2.5 rounded-full bg-red-500 shadow-[0_0_15px_rgba(239,68,68,0.8)]" />
          <span className="font-serif text-xs uppercase tracking-[0.16em] text-red-200">Luxury Workspace</span>
        </div>
        <h1 className="font-serif text-4xl font-semibold tracking-tight text-red-100">Brownfield Cartographer</h1>
        <p className="mt-3 text-sm text-zinc-300">
          Initializing workspace and loading your latest repository analysis.
        </p>

        <div className="mt-6 flex items-center justify-center gap-2">
          <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-red-400" />
          <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-red-500 [animation-delay:120ms]" />
          <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-red-600 [animation-delay:220ms]" />
        </div>

        <div className="mt-6 rounded-xl border border-red-900/70 bg-zinc-950/70 px-4 py-3 text-left text-xs text-zinc-300 shadow-[0_18px_45px_rgba(0,0,0,0.45)]">
          <p><span className="text-zinc-500">API:</span> <span className="font-mono text-zinc-300">{API_BASE}</span></p>
          {loading && <p className="mt-1 text-red-200">Loading analyses...</p>}
          {error && <p className="mt-1 text-red-300">{error}</p>}
          {!loading && !error && (
            <p className="mt-1 text-zinc-300">Found {analyses.length} analyses. Redirecting...</p>
          )}
        </div>
      </div>
    </div>
  );
}
