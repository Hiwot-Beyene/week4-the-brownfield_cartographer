"use client";

import { type ChangeEvent, useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { GraphPanel, type GraphPayload } from "@/components/GraphPanel";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface Analysis {
  id: number;
  repo_id: string;
  repo_path: string;
  commit_sha: string | null;
  run_at: string;
}

interface DayOneCitation {
  file: string;
  line?: number | null;
}

interface DayOneAnswer {
  question_id: string;
  answer: string;
  citations: DayOneCitation[];
}

type WorkspaceTab = "surveyor" | "hydrologist" | "semanticist";

const AGENTS: { id: WorkspaceTab; label: string; description: string }[] = [
  { id: "surveyor", label: "Surveyor", description: "Module topology, centrality, and dead-code hotspots." },
  { id: "hydrologist", label: "Hydrologist", description: "Data lineage: tables, transformations, and flows." },
  { id: "semanticist", label: "Semanticist", description: "Purpose statements, domains, and Day-One answers." },
];

function repoDisplayName(repoPath: string): string {
  const normalized = repoPath.replace(/\\/g, "/").trim();
  const segments = normalized.split("/").filter(Boolean);
  return segments.length > 0 ? segments[segments.length - 1] : repoPath || "Repository";
}

export default function AnalysisDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;

  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [currentAnalysis, setCurrentAnalysis] = useState<Analysis | null>(null);
  const [moduleGraph, setModuleGraph] = useState<GraphPayload | null>(null);
  const [lineageGraph, setLineageGraph] = useState<GraphPayload | null>(null);
  const [dayOneAnswers, setDayOneAnswers] = useState<DayOneAnswer[]>([]);
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("surveyor");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const analysisId = id ? parseInt(String(id), 10) : null;

  const loadAnalyses = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/analyses?limit=100`);
      if (!res.ok) throw new Error("Failed to load analyses");
      const data = await res.json();
      setAnalyses(Array.isArray(data) ? data : []);
    } catch {
      setAnalyses([]);
    }
  }, []);

  useEffect(() => {
    loadAnalyses();
  }, [loadAnalyses]);

  useEffect(() => {
    if (!analysisId || !Number.isInteger(analysisId)) return;
    const fromList = analyses.find((a) => a.id === analysisId) ?? null;
    if (fromList) {
      setCurrentAnalysis(fromList);
      return;
    }
    let cancelled = false;
    fetch(`${API_BASE}/analyses/${analysisId}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (cancelled || !data?.analysis) return;
        setCurrentAnalysis(data.analysis);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [analysisId, analyses]);

  useEffect(() => {
    if (!analysisId || !Number.isInteger(analysisId)) return;
    let cancelled = false;
    setError(null);
    setLoading(true);
    async function load() {
      try {
        const [modGraphRes, linGraphRes, answersRes] = await Promise.all([
          fetch(`${API_BASE}/analyses/${analysisId}/module-graph`),
          fetch(`${API_BASE}/analyses/${analysisId}/lineage-graph`),
          fetch(`${API_BASE}/analyses/${analysisId}/day-one-answers`),
        ]);
        if (cancelled) return;
        const modPayload: GraphPayload | null = modGraphRes.ok ? await modGraphRes.json() : null;
        const linPayload: GraphPayload | null = linGraphRes.ok ? await linGraphRes.json() : null;
        let answers: DayOneAnswer[] = [];
        if (answersRes.ok) {
          const raw = await answersRes.json();
          answers = Array.isArray(raw) ? raw : raw?.answers ?? [];
        }
        setModuleGraph(modPayload);
        setLineageGraph(linPayload);
        setDayOneAnswers(answers);
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [analysisId]);

  const handleRepoChange = (e: ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value;
    if (value) router.push(`/analyses/${value}`);
  };

  const activeAgent = AGENTS.find((a) => a.id === activeTab);

  return (
    <div className="flex min-h-screen flex-col text-zinc-100">
      <div className="pointer-events-none fixed inset-0 -z-10 bg-[radial-gradient(circle_at_8%_-8%,rgba(239,68,68,0.28),transparent_40%),radial-gradient(circle_at_86%_0%,rgba(185,28,28,0.24),transparent_42%),radial-gradient(circle_at_50%_120%,rgba(127,29,29,0.32),transparent_45%),linear-gradient(to_bottom,#070708,#171719)]" />
      <nav
        aria-label="System navigation"
        className="sticky top-0 z-30 border-b border-red-900/70 bg-zinc-950/80 backdrop-blur-2xl"
      >
        <div className="mx-auto flex w-full max-w-[1540px] flex-wrap items-center gap-3 px-4 py-3">
          <div className="mr-2 hidden items-center gap-2 rounded-xl border border-red-900/70 bg-gradient-to-r from-zinc-900/90 to-zinc-900/60 px-3 py-2 shadow-[0_18px_45px_rgba(0,0,0,0.45)] sm:flex">
            <span className="h-2.5 w-2.5 rounded-full bg-red-500 shadow-[0_0_18px_rgba(239,68,68,0.9)]" />
            <span className="font-serif text-xs font-semibold uppercase tracking-[0.18em] text-red-100">
              Brownfield Cartographer
            </span>
          </div>

          <div className="flex items-center gap-2 rounded-xl border border-red-900/70 bg-zinc-900/85 px-3 py-2 shadow-[0_18px_45px_rgba(0,0,0,0.45)]">
            <label
              htmlFor="repo-select"
              className="text-[11px] font-semibold uppercase tracking-[0.14em] text-red-300/90"
            >
              Repository
            </label>
            <select
              id="repo-select"
              value={analysisId ?? ""}
              onChange={handleRepoChange}
              aria-label="Select repository"
              className="min-w-[220px] rounded-lg border border-red-800/60 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-100 outline-none ring-red-500 transition focus:ring-2"
            >
              {analyses.length === 0 && <option value="">No analyses</option>}
              {analyses.map((a) => (
                <option key={a.id} value={a.id}>
                  {repoDisplayName(a.repo_path)}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-1 rounded-xl border border-red-900/70 bg-zinc-900/85 p-1 shadow-[0_18px_45px_rgba(0,0,0,0.45)]">
            {AGENTS.map((a) => (
              <button
                key={a.id}
                type="button"
                role="tab"
                aria-selected={activeTab === a.id}
                onClick={() => setActiveTab(a.id)}
                className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
                  activeTab === a.id
                    ? "bg-gradient-to-r from-red-700 to-red-600 text-white shadow-[0_0_0_1px_rgba(252,165,165,0.5),0_0_30px_rgba(185,28,28,0.35)]"
                    : "text-zinc-300 hover:bg-zinc-800 hover:text-red-200"
                }`}
              >
                {a.label}
              </button>
            ))}
          </div>

          <div className="ml-auto hidden text-xs text-zinc-400 md:block">
            <span className="rounded-full border border-red-900/70 bg-zinc-900/70 px-3 py-1 shadow-[0_18px_45px_rgba(0,0,0,0.45)]">
              Repo:{" "}
              <span className="font-medium text-red-100">
                {currentAnalysis ? repoDisplayName(currentAnalysis.repo_path) : "Loading..."}
              </span>
            </span>
          </div>
        </div>
      </nav>

      <main className="mx-auto w-full max-w-[1540px] flex-1 p-4 md:p-6">
        <section className="mb-5 rounded-2xl border border-red-900/70 bg-gradient-to-br from-zinc-900/90 to-zinc-900/60 p-6 shadow-[0_18px_45px_rgba(0,0,0,0.45)]">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-red-300/90">Workspace</p>
              <h1 className="font-serif mt-1 text-3xl font-semibold tracking-tight text-red-100">
                {currentAnalysis ? repoDisplayName(currentAnalysis.repo_path) : "Loading repository..."}
              </h1>
              <p className="mt-2 max-w-2xl text-sm text-zinc-300">{activeAgent?.description}</p>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className="rounded-full border border-red-900/70 bg-zinc-950/80 px-3 py-1 text-zinc-300 shadow-[0_18px_45px_rgba(0,0,0,0.45)]">
                Analysis #{analysisId ?? "-"}
              </span>
              <span className="rounded-full border border-red-900/70 bg-zinc-950/80 px-3 py-1 text-red-200 shadow-[0_18px_45px_rgba(0,0,0,0.45)]">
                {activeAgent?.label}
              </span>
            </div>
          </div>

        </section>

        {error && (
          <div
            className="mb-4 rounded-xl border border-red-700 bg-red-950/40 p-3 text-sm text-red-200"
            role="alert"
          >
            {error}
          </div>
        )}

        {activeTab === "surveyor" && (
          <GraphPanel title="Module Dependency Graph" graphKind="module" graph={!loading ? moduleGraph : null} />
        )}

        {activeTab === "hydrologist" && (
          <GraphPanel title="Data Lineage Graph" graphKind="lineage" graph={!loading ? lineageGraph : null} />
        )}

        {activeTab === "semanticist" && (
          <section className="rounded-2xl border border-red-900/70 bg-gradient-to-br from-zinc-900/90 to-zinc-900/60 p-5 shadow-[0_18px_45px_rgba(0,0,0,0.45)]">
            <h2 className="font-serif text-2xl font-semibold text-red-100">{activeAgent?.label ?? "Semanticist"}</h2>
            <p className="mt-1 text-sm text-zinc-300">{activeAgent?.description ?? ""}</p>
            {loading ? (
              <p className="mt-4 text-sm text-zinc-400">Loading...</p>
            ) : dayOneAnswers.length === 0 ? (
              <p className="mt-4 text-sm text-zinc-400">No Day-One answers for this analysis yet.</p>
            ) : (
              <ul className="mt-4 grid gap-3 md:grid-cols-2">
                {dayOneAnswers.map((a) => (
                  <li
                    key={a.question_id}
                    className="rounded-xl border border-red-950/70 bg-gradient-to-b from-zinc-950 to-zinc-900 p-4 shadow-[0_18px_45px_rgba(0,0,0,0.45)]"
                  >
                    <p className="text-xs font-semibold uppercase tracking-wide text-red-300">{a.question_id}</p>
                    <p className="mt-2 text-sm leading-6 text-zinc-200">{a.answer}</p>
                    {a.citations?.length > 0 && (
                      <ul className="mt-3 grid gap-1">
                        {a.citations.map((c, i) => (
                          <li key={`${c.file}-${c.line ?? "x"}-${i}`} className="font-mono text-xs text-zinc-400">
                            {c.file}
                            {c.line != null ? `:${c.line}` : ""}
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
