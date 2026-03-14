"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";
import { forceCollide } from "d3-force";

// Use the dedicated 2D build which has no AFRAME/THREE VR dependencies.
const ForceGraph2D = dynamic(
  () => import("react-force-graph-2d"),
  { ssr: false }
);

export type GraphKind = "module" | "lineage";

export interface GraphNode {
  id: string;
  label?: string;
  size?: number;
  node_type?: string;
  dead_code?: boolean;
  important?: boolean;
  [key: string]: unknown;
}

export interface GraphEdge {
  from: string;
  to: string;
  [key: string]: unknown;
}

export interface GraphPayload {
  nodes: GraphNode[];
  edges: GraphEdge[];
  hubs?: string[];
  sources?: string[];
  sinks?: string[];
  filtered_isolated_nodes?: number;
  filtered_isolated_regular_modules?: number;
}

function toDisplayName(value: string): string {
  const normalized = String(value || "").replaceAll("\\", "/");
  const parts = normalized.split("/").filter(Boolean);
  return parts.length ? parts[parts.length - 1] : normalized;
}

function toDisplayNameWithContext(value: string, duplicateBasenames: Set<string>): string {
  const normalized = String(value || "").replaceAll("\\", "/");
  const parts = normalized.split("/").filter(Boolean);
  if (parts.length === 0) return normalized;
  const base = parts[parts.length - 1];
  if (!duplicateBasenames.has(base)) return base;
  if (parts.length >= 2) return `${parts[parts.length - 2]}/${base}`;
  return base;
}

function nodeIdFromUnknown(value: unknown): string {
  if (typeof value === "string") return value;
  if (value && typeof value === "object" && "id" in (value as Record<string, unknown>)) {
    return String((value as Record<string, unknown>).id);
  }
  return String(value ?? "");
}

function edgeKeyFromUnknown(link: any): string {
  const source = nodeIdFromUnknown(link?.source ?? link?.from);
  const target = nodeIdFromUnknown(link?.target ?? link?.to);
  return `${source}->${target}`;
}

function edgeDisplayLabel(link: any): string {
  const raw = link?.label ?? link?.type ?? link?.edge_type;
  if (raw) return String(raw);
  const source = toDisplayName(nodeIdFromUnknown(link?.source ?? link?.from));
  const target = toDisplayName(nodeIdFromUnknown(link?.target ?? link?.to));
  return `${source} -> ${target}`;
}

interface GraphPanelProps {
  title: string;
  graphKind: GraphKind;
  graph: GraphPayload | null;
}

type LegendFilter =
  | "dead_code"
  | "most_connected"
  | "important"
  | "regular_module"
  | "dataset"
  | "transformation"
  | "other"
  | "lineage_start"
  | "lineage_end"
  | "main_flow";

type ModuleCategory = "dead_code" | "most_connected" | "important" | "regular_module";
type LineageCategory = "dataset" | "transformation" | "other";
type NodeCategory = ModuleCategory | LineageCategory;

function getNodeCategory(node: GraphNode, graphKind: GraphKind): NodeCategory {
  if (graphKind === "module") {
    // Canonical, exclusive category order avoids ambiguous coloring/filtering.
    if (Boolean(node.dead_code)) return "dead_code";
    if (Boolean(node.is_most_connected)) return "most_connected";
    if (Boolean(node.important)) return "important";
    return "regular_module";
  }
  if (node.node_type === "dataset") return "dataset";
  if (node.node_type === "transformation") return "transformation";
  return "other";
}

function matchesLegend(node: GraphNode, graphKind: GraphKind, filter: LegendFilter | null): boolean {
  if (!filter) return true;
  if (filter === "lineage_start") return Boolean(node.is_lineage_start);
  if (filter === "lineage_end") return Boolean(node.is_lineage_end);
  if (filter === "main_flow") return Boolean(node.is_main_flow);
  return getNodeCategory(node, graphKind) === filter;
}

function nodeColor(node: GraphNode, graphKind: GraphKind, activeFilter: LegendFilter | null): string {
  const dimmed = activeFilter && !matchesLegend(node, graphKind, activeFilter);
  if (dimmed) return "#3f3f46";

  const category = getNodeCategory(node, graphKind);
  if (category === "dead_code") return "#fb7185";
  if (category === "most_connected") return "#22c55e";
  if (category === "important") return "#f97316";
  if (category === "regular_module") return "#e4e4e7";
  if (Boolean(node.is_lineage_start)) return "#4ade80";
  if (Boolean(node.is_lineage_end)) return "#a78bfa";
  if (category === "dataset") return "#fca5a5";
  if (category === "transformation") return "#fb7185";
  return "#d4d4d8";
}

export function GraphPanel({ title, graphKind, graph }: GraphPanelProps) {
  const fgRef = useRef<any>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [showLabels, setShowLabels] = useState(true);
  const [activeFilter, setActiveFilter] = useState<LegendFilter | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeKey, setSelectedEdgeKey] = useState<string | null>(null);
  const [selectedEdgeNodes, setSelectedEdgeNodes] = useState<{ source: string; target: string } | null>(null);

  const graphData = useMemo(() => {
    if (!graph) return { nodes: [], links: [] };
    const basenameCount = new Map<string, number>();
    for (const n of graph.nodes) {
      const base = toDisplayName(String(n.label ?? n.id));
      basenameCount.set(base, (basenameCount.get(base) ?? 0) + 1);
    }
    const duplicateBasenames = new Set(
      Array.from(basenameCount.entries())
        .filter(([, count]) => count > 1)
        .map(([name]) => name)
    );

    const nodeIds = new Set(graph.nodes.map((n) => n.id));
    const degreeById = new Map<string, number>();
    for (const edge of graph.edges) {
      degreeById.set(edge.from, (degreeById.get(edge.from) ?? 0) + 1);
      degreeById.set(edge.to, (degreeById.get(edge.to) ?? 0) + 1);
    }
    const nodeById = new Map(graph.nodes.map((n) => [n.id, n] as const));
    const liveDegreeEntries = Array.from(degreeById.entries()).filter(([id]) => {
      const n = nodeById.get(id);
      return !n?.dead_code;
    });
    const maxDegree = Math.max(0, ...liveDegreeEntries.map(([, degree]) => degree));
    const inferredMostConnectedIds = new Set(
      maxDegree > 0
        ? liveDegreeEntries
            .filter(([, degree]) => degree === maxDegree)
            .map(([id]) => id)
        : []
    );
    // "Most connected" should reflect actual connectivity first (degree), not only backend hub hint.
    const mostConnectedIds = new Set(
      inferredMostConnectedIds.size > 0
        ? Array.from(inferredMostConnectedIds)
        : (graph.hubs || []).filter((id) => nodeIds.has(id)).slice(0, 1)
    );

    const outById = new Map<string, number>();
    const inById = new Map<string, number>();
    const adj = new Map<string, string[]>();
    const rev = new Map<string, string[]>();
    const datasetIds = new Set(
      graph.nodes
        .filter((n) => String(n.node_type || "") === "dataset")
        .map((n) => n.id)
    );
    for (const id of nodeIds) {
      outById.set(id, 0);
      inById.set(id, 0);
      adj.set(id, []);
      rev.set(id, []);
    }
    for (const e of graph.edges) {
      if (!nodeIds.has(e.from) || !nodeIds.has(e.to)) continue;
      outById.set(e.from, (outById.get(e.from) ?? 0) + 1);
      inById.set(e.to, (inById.get(e.to) ?? 0) + 1);
      adj.get(e.from)?.push(e.to);
      rev.get(e.to)?.push(e.from);
    }
    // Start/End for lineage should be dataset boundaries (not transformation internals).
    let lineageStartIds = new Set((graph.sources || []).filter((id) => datasetIds.has(id)));
    let lineageEndIds = new Set((graph.sinks || []).filter((id) => datasetIds.has(id)));
    if (lineageStartIds.size === 0) {
      lineageStartIds = new Set(
        Array.from(datasetIds).filter((id) => (inById.get(id) ?? 0) === 0 && (outById.get(id) ?? 0) > 0)
      );
    }
    if (lineageEndIds.size === 0) {
      lineageEndIds = new Set(
        Array.from(datasetIds).filter((id) => (outById.get(id) ?? 0) === 0 && (inById.get(id) ?? 0) > 0)
      );
    }
    if (lineageStartIds.size === 0) {
      const sourceCandidates = Array.from(datasetIds).filter((id) => (outById.get(id) ?? 0) > 0);
      const minIn = sourceCandidates.length
        ? Math.min(...sourceCandidates.map((id) => inById.get(id) ?? 0))
        : 0;
      lineageStartIds = new Set(
        sourceCandidates.filter((id) => (inById.get(id) ?? 0) === minIn)
      );
    }
    if (lineageEndIds.size === 0) {
      const sinkCandidates = Array.from(datasetIds).filter((id) => (inById.get(id) ?? 0) > 0);
      const minOut = sinkCandidates.length
        ? Math.min(...sinkCandidates.map((id) => outById.get(id) ?? 0))
        : 0;
      lineageEndIds = new Set(
        sinkCandidates.filter((id) => (outById.get(id) ?? 0) === minOut)
      );
    }

    const reachableFromStarts = new Set<string>();
    const stackA = Array.from(lineageStartIds);
    while (stackA.length) {
      const cur = stackA.pop()!;
      if (reachableFromStarts.has(cur)) continue;
      reachableFromStarts.add(cur);
      for (const nxt of adj.get(cur) || []) stackA.push(nxt);
    }
    const canReachEnds = new Set<string>();
    const stackB = Array.from(lineageEndIds);
    while (stackB.length) {
      const cur = stackB.pop()!;
      if (canReachEnds.has(cur)) continue;
      canReachEnds.add(cur);
      for (const prev of rev.get(cur) || []) stackB.push(prev);
    }
    const mainFlowNodeIds = new Set(
      Array.from(nodeIds).filter((id) => reachableFromStarts.has(id) && canReachEnds.has(id))
    );

    return {
      nodes: graph.nodes.map((node) => ({
        ...node,
        is_most_connected: mostConnectedIds.has(node.id),
        is_lineage_start: lineageStartIds.has(node.id),
        is_lineage_end: lineageEndIds.has(node.id),
        is_main_flow: mainFlowNodeIds.has(node.id),
        category: getNodeCategory({ ...node, is_most_connected: mostConnectedIds.has(node.id) } as GraphNode, graphKind),
        label: showLabels ? toDisplayNameWithContext(String(node.label ?? node.id), duplicateBasenames) : "",
      })),
      links: graph.edges.map((edge) => ({
        source: edge.from,
        target: edge.to,
        is_main_flow: mainFlowNodeIds.has(edge.from) && mainFlowNodeIds.has(edge.to),
        ...edge,
      })),
    };
  }, [graph, showLabels]);

  const nodeCount = graph?.nodes.length ?? 0;
  const edgeCount = graph?.edges.length ?? 0;
  const selectedCount = graphData.nodes.filter((node) => matchesLegend(node as GraphNode, graphKind, activeFilter)).length;
  const lineageInsights = useMemo(() => {
    if (graphKind !== "lineage") return null;
    const nodes = graphData.nodes as Array<any>;
    const starts = nodes.filter((n) => n.is_lineage_start);
    const ends = nodes.filter((n) => n.is_lineage_end);
    const main = nodes.filter((n) => n.is_main_flow);
    return {
      startCount: starts.length,
      endCount: ends.length,
      mainCount: main.length,
      startLabels: starts.slice(0, 3).map((n) => String(n.label || n.id)),
      endLabels: ends.slice(0, 3).map((n) => String(n.label || n.id)),
    };
  }, [graphKind, graphData]);
  const highlightedNodeIds = useMemo(() => {
    const set = new Set<string>();
    if (selectedNodeId) set.add(selectedNodeId);
    if (selectedEdgeNodes) {
      set.add(selectedEdgeNodes.source);
      set.add(selectedEdgeNodes.target);
    }
    return set;
  }, [selectedNodeId, selectedEdgeNodes]);

  useEffect(() => {
    if (!fgRef.current || nodeCount === 0) return;
    const fg = fgRef.current;
    try {
      // Tune forces for readability: prevent overlap while preserving connectivity.
      fg.d3Force("charge")?.strength(-145);
      fg.d3Force("link")?.distance(92)?.strength(0.58);
      fg.d3Force("center")?.strength(0.08);
      fg.d3Force("collide", forceCollide().radius((n: any) => Math.max(7, (n?.size ?? 4) + 5)).strength(0.9));
      fg.d3VelocityDecay?.(0.28);
      fg.d3ReheatSimulation?.();
    } catch {
      // Keep rendering even if underlying force engine API differs.
    }
  }, [nodeCount, edgeCount, graphKind]);

  useEffect(() => {
    if (!fgRef.current || !activeFilter) return;
    const timer = setTimeout(() => {
      fgRef.current?.zoomToFit(700, 90, (node: any) =>
        matchesLegend(node as GraphNode, graphKind, activeFilter)
      );
    }, 120);
    return () => clearTimeout(timer);
  }, [activeFilter, graphData, graphKind]);

  function fitGraph() {
    fgRef.current?.zoomToFit(600, 40);
  }

  function zoomIn() {
    fgRef.current?.zoom(1.2, 400);
  }

  function zoomOut() {
    fgRef.current?.zoom(0.8, 400);
  }

  function resetView() {
    fgRef.current?.zoomToFit(600, 60);
  }

  function searchNode() {
    if (!graph || !fgRef.current) return;
    const term = searchTerm.trim().toLowerCase();
    if (!term) return;
    const match = graph.nodes.find(
      (node) =>
        node.id.toLowerCase().includes(term) ||
        String(node.label || "").toLowerCase().includes(term)
    );
    if (!match) return;
    fgRef.current.zoomToFit(700, 80, (node: any) => node.id === match.id);
  }

  return (
    <section className="grid h-[78vh] min-h-[500px] grid-rows-[auto_auto_minmax(0,1fr)] gap-3 rounded-2xl border border-red-900/70 bg-gradient-to-br from-zinc-900/90 to-zinc-900/60 p-4 shadow-[0_18px_45px_rgba(0,0,0,0.45)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-red-300/90">Interactive Graph</p>
          <h3 className="font-serif mt-1 text-xl font-semibold text-red-100">{title}</h3>
        </div>
        <div className="flex flex-wrap gap-2">
          <input
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder="Search node"
            aria-label="Search node"
            className="h-9 min-w-[190px] rounded-lg border border-red-800/60 bg-zinc-950/90 px-3 text-sm text-zinc-100 outline-none ring-red-500 transition focus:ring-2"
          />
          <button
            className="h-9 rounded-lg bg-gradient-to-r from-red-700 to-red-600 px-3 text-sm font-medium text-white transition hover:from-red-600 hover:to-red-500"
            onClick={searchNode}
          >
            Search
          </button>
          <button className="h-9 rounded-lg border border-zinc-700 bg-zinc-800/90 px-3 text-sm text-zinc-200 hover:border-red-700/70 hover:text-red-200" onClick={zoomIn}>Zoom +</button>
          <button className="h-9 rounded-lg border border-zinc-700 bg-zinc-800/90 px-3 text-sm text-zinc-200 hover:border-red-700/70 hover:text-red-200" onClick={zoomOut}>Zoom -</button>
          <button className="h-9 rounded-lg border border-zinc-700 bg-zinc-800/90 px-3 text-sm text-zinc-200 hover:border-red-700/70 hover:text-red-200" onClick={fitGraph}>Fit</button>
          <button className="h-9 rounded-lg border border-zinc-700 bg-zinc-800/90 px-3 text-sm text-zinc-200 hover:border-red-700/70 hover:text-red-200" onClick={resetView}>Reset</button>
          <button className="h-9 rounded-lg border border-zinc-700 bg-zinc-800/90 px-3 text-sm text-zinc-200 hover:border-red-700/70 hover:text-red-200" onClick={() => setShowLabels((value) => !value)}>
            {showLabels ? "Hide labels" : "Show labels"}
          </button>
        </div>
      </div>
      <div className="flex flex-wrap gap-2 text-xs text-zinc-200">
        <span className="rounded-full border border-red-900/70 bg-zinc-950/80 px-3 py-1 shadow-[0_18px_45px_rgba(0,0,0,0.45)]">{nodeCount} nodes</span>
        <span className="rounded-full border border-red-900/70 bg-zinc-950/80 px-3 py-1 shadow-[0_18px_45px_rgba(0,0,0,0.45)]">{edgeCount} edges</span>
        {graph?.filtered_isolated_regular_modules ? (
          <span className="rounded-full border border-zinc-700 bg-zinc-900/70 px-3 py-1 text-zinc-300">
            hidden isolated modules: {graph.filtered_isolated_regular_modules}
          </span>
        ) : null}
        {graph?.filtered_isolated_nodes ? (
          <span className="rounded-full border border-zinc-700 bg-zinc-900/70 px-3 py-1 text-zinc-300">
            hidden isolated nodes: {graph.filtered_isolated_nodes}
          </span>
        ) : null}
        {activeFilter ? (
          <button
            className="rounded-full border border-green-700/80 bg-green-900/30 px-3 py-1 text-green-200 hover:bg-green-900/45"
            onClick={() => setActiveFilter(null)}
          >
            Selected: {selectedCount} (click to clear)
          </button>
        ) : null}
        {graphKind === "module" ? (
          <>
            <button
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 ${activeFilter === "dead_code" ? "border-rose-500 bg-rose-900/30 text-rose-100" : "border-red-900/70 bg-zinc-950/80"}`}
              onClick={() => setActiveFilter((prev) => (prev === "dead_code" ? null : "dead_code"))}
            >
              <span className="h-2.5 w-2.5 rounded-full bg-rose-400" />
              Dead code
            </button>
            <button
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 ${activeFilter === "most_connected" ? "border-green-500 bg-green-900/30 text-green-100" : "border-red-900/70 bg-zinc-950/80"}`}
              onClick={() => setActiveFilter((prev) => (prev === "most_connected" ? null : "most_connected"))}
            >
              <span className="h-2.5 w-2.5 rounded-full bg-green-500" />
              Most connected
            </button>
            <button
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 ${activeFilter === "important" ? "border-orange-500 bg-orange-900/30 text-orange-100" : "border-red-900/70 bg-zinc-950/80"}`}
              onClick={() => setActiveFilter((prev) => (prev === "important" ? null : "important"))}
            >
              <span className="h-2.5 w-2.5 rounded-full bg-orange-500" />
              Important
            </button>
            <button
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 ${activeFilter === "regular_module" ? "border-zinc-400 bg-zinc-800/90 text-zinc-100" : "border-red-900/70 bg-zinc-950/80"}`}
              onClick={() => setActiveFilter((prev) => (prev === "regular_module" ? null : "regular_module"))}
            >
              <span className="h-2.5 w-2.5 rounded-full bg-zinc-300" />
              Regular module
            </button>
          </>
        ) : (
          <>
            <button
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 ${activeFilter === "dataset" ? "border-rose-300 bg-rose-900/30 text-rose-100" : "border-red-900/70 bg-zinc-950/80"}`}
              onClick={() => setActiveFilter((prev) => (prev === "dataset" ? null : "dataset"))}
            >
              <span className="h-2.5 w-2.5 rounded-full bg-rose-300" />
              Dataset
            </button>
            <button
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 ${activeFilter === "transformation" ? "border-rose-500 bg-rose-900/30 text-rose-100" : "border-red-900/70 bg-zinc-950/80"}`}
              onClick={() => setActiveFilter((prev) => (prev === "transformation" ? null : "transformation"))}
            >
              <span className="h-2.5 w-2.5 rounded-full bg-rose-400" />
              Transformation
            </button>
            <button
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 ${activeFilter === "other" ? "border-zinc-400 bg-zinc-800/90 text-zinc-100" : "border-red-900/70 bg-zinc-950/80"}`}
              onClick={() => setActiveFilter((prev) => (prev === "other" ? null : "other"))}
            >
              <span className="h-2.5 w-2.5 rounded-full bg-zinc-300" />
              Other
            </button>
            <button
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 ${activeFilter === "lineage_start" ? "border-green-500 bg-green-900/30 text-green-100" : "border-red-900/70 bg-zinc-950/80"}`}
              onClick={() => setActiveFilter((prev) => (prev === "lineage_start" ? null : "lineage_start"))}
            >
              <span className="h-2.5 w-2.5 rounded-full bg-green-400" />
              Start
            </button>
            <button
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 ${activeFilter === "lineage_end" ? "border-violet-500 bg-violet-900/30 text-violet-100" : "border-red-900/70 bg-zinc-950/80"}`}
              onClick={() => setActiveFilter((prev) => (prev === "lineage_end" ? null : "lineage_end"))}
            >
              <span className="h-2.5 w-2.5 rounded-full bg-violet-400" />
              End
            </button>
            <button
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 ${activeFilter === "main_flow" ? "border-emerald-500 bg-emerald-900/30 text-emerald-100" : "border-red-900/70 bg-zinc-950/80"}`}
              onClick={() => setActiveFilter((prev) => (prev === "main_flow" ? null : "main_flow"))}
            >
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
              Main flow
            </button>
          </>
        )}
      </div>
      {graphKind === "lineage" && lineageInsights ? (
        <div className="rounded-xl border border-emerald-900/60 bg-zinc-950/65 px-3 py-2 text-xs text-zinc-300">
          <p className="text-emerald-200">
            Main flow: data starts at source datasets (no upstream producer) and ends at sink datasets (no downstream consumer).
          </p>
          <p className="mt-1">
            Starts: {lineageInsights.startCount}
            {lineageInsights.startLabels.length ? ` - ${lineageInsights.startLabels.join(", ")}` : ""}
          </p>
          <p>
            Ends: {lineageInsights.endCount}
            {lineageInsights.endLabels.length ? ` - ${lineageInsights.endLabels.join(", ")}` : ""}
          </p>
          <p>Main-flow nodes: {lineageInsights.mainCount}</p>
        </div>
      ) : null}
      <div className="h-full min-h-0 overflow-hidden rounded-xl border border-red-900/70 bg-zinc-950 shadow-[0_18px_45px_rgba(0,0,0,0.45)]">
        {nodeCount > 0 ? (
          <ForceGraph2D
            ref={fgRef}
            graphData={graphData}
            nodeRelSize={5}
            nodeVal={(node: any) => node.size ?? 4}
            nodeLabel={(node: any) =>
              showLabels
                ? String((node.label as string) || (node.id as string))
                : ""
            }
            nodeColor={(node: any) => {
              const nodeId = String(node?.id ?? "");
              if (highlightedNodeIds.size > 0 && !highlightedNodeIds.has(nodeId)) {
                return "#3f3f46";
              }
              if (selectedNodeId && selectedNodeId === nodeId) return "#38bdf8";
              return nodeColor(node as GraphNode, graphKind, activeFilter);
            }}
            nodeCanvasObjectMode={() => "after"}
            nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
              if (!showLabels) return;
              const nodeId = String(node?.id ?? "");
              const selectedOrMatched =
                highlightedNodeIds.has(nodeId) ||
                (activeFilter ? matchesLegend(node as GraphNode, graphKind, activeFilter) : false);
              if (!selectedOrMatched && globalScale < 1.65) return;
              if (activeFilter && !matchesLegend(node as GraphNode, graphKind, activeFilter)) return;
              const label = String(node?.label || node?.id || "");
              if (!label) return;
              const fontSize = Math.max(7, 11 / globalScale);
              ctx.font = `${fontSize}px Inter, sans-serif`;
              ctx.fillStyle = "rgba(244, 244, 245, 0.96)";
              ctx.textAlign = "center";
              ctx.textBaseline = "middle";
              const x = Number(node?.x ?? 0);
              const y = Number(node?.y ?? 0) + Math.max(8, Number(node?.size ?? 4) + 5);
              ctx.fillText(label, x, y);
            }}
            linkColor={(link: any) => {
              if (!selectedEdgeKey) {
                if (graphKind === "lineage") {
                  if (activeFilter === "main_flow") {
                    return link?.is_main_flow ? "rgba(16, 185, 129, 0.95)" : "rgba(63, 63, 70, 0.38)";
                  }
                  if (link?.is_main_flow) return "rgba(16, 185, 129, 0.88)";
                  const edgeType = String(link?.edge_type ?? "").toUpperCase();
                  if (edgeType === "PRODUCES" || Boolean(link?.is_write)) return "rgba(16, 185, 129, 0.84)";
                  return "rgba(59, 130, 246, 0.8)";
                }
                return "rgba(37, 99, 235, 0.8)";
              }
              return edgeKeyFromUnknown(link) === selectedEdgeKey
                ? "rgba(74, 222, 128, 0.95)"
                : "rgba(63, 63, 70, 0.5)";
            }}
            linkWidth={(link: any) => {
              if (selectedEdgeKey && edgeKeyFromUnknown(link) === selectedEdgeKey) return 3;
              if (graphKind === "lineage" && link?.is_main_flow) return 2.4;
              if (graphKind === "module") {
                const w = Number(link?.weight ?? 1);
                return Math.min(3, 1.1 + Math.log2(Math.max(1, w)) * 0.65);
              }
              return 1.4;
            }}
            linkCurvature={0.22}
            linkCanvasObjectMode={() => (showLabels ? "after" : undefined)}
            linkCanvasObject={(link: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
              if (!showLabels) return;
              if (!selectedEdgeKey && globalScale < 2.3) return;
              const start = link?.source;
              const end = link?.target;
              if (!start || !end || start.x == null || start.y == null || end.x == null || end.y == null) return;

              const label = edgeDisplayLabel(link);
              if (!label) return;

              const mx = (start.x + end.x) / 2;
              const my = (start.y + end.y) / 2;
              ctx.save();
              ctx.font = "10px Inter, sans-serif";
              ctx.fillStyle = "rgba(254, 202, 202, 0.92)";
              ctx.textAlign = "center";
              ctx.textBaseline = "middle";
              ctx.fillText(label, mx, my);
              ctx.restore();
            }}
            backgroundColor="#09090b"
            onNodeClick={(node: any) => {
              const id = nodeIdFromUnknown(node);
              setSelectedNodeId((prev) => (prev === id ? null : id));
              setSelectedEdgeKey(null);
              setSelectedEdgeNodes(null);
            }}
            onLinkClick={(link: any) => {
              const key = edgeKeyFromUnknown(link);
              const source = nodeIdFromUnknown(link?.source ?? link?.from);
              const target = nodeIdFromUnknown(link?.target ?? link?.to);
              setSelectedEdgeKey((prev) => (prev === key ? null : key));
              setSelectedNodeId(null);
              setSelectedEdgeNodes((prev) => (prev && `${prev.source}->${prev.target}` === key ? null : { source, target }));
            }}
            onBackgroundClick={() => {
              setSelectedNodeId(null);
              setSelectedEdgeKey(null);
              setSelectedEdgeNodes(null);
            }}
          />
        ) : (
          <div className="grid h-full place-items-center p-6 text-center text-sm text-zinc-400">
            <p>No graph data available for this analysis.</p>
          </div>
        )}
      </div>
    </section>
  );
}

