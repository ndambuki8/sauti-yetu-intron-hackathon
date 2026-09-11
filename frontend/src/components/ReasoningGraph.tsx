import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  type ReactFlowInstance,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { Graph, Provenance } from "../api/types";
import {
  NODE_COLORS,
  NODE_KIND_LABELS,
  NODE_TEXT_COLORS,
  NODE_TINTS,
  type NodeKind,
} from "../lib/palette";
import { useConsultation } from "../state/consultation";
import { SourceCitation } from "./Provenance";
import Tooltip, { InfoIcon } from "./Tooltip";

const KIND_ORDER: NodeKind[] = [
  "symptom",
  "finding",
  "condition",
  "red_flag",
  "topic",
  "department",
];

const PATIENT_ID = "patient:patient";

interface NodeData extends Record<string, unknown> {
  label: string;
  kind: NodeKind;
  turn: number;
  source?: Provenance;
  isNew?: boolean;
  probability?: number;
}

/** A Miro-style card node: rounded, tinted by clinical kind, soft shadow.
 * Condition nodes carry a probability: a % badge, a fill bar, and a font/border
 * that grows with confidence, so likelier diagnoses read as larger. */
function TriageNode({ data, selected }: NodeProps<Node<NodeData>>) {
  const kind = data.kind;
  const hasProb = kind === "condition" && typeof data.probability === "number";
  const prob = hasProb ? (data.probability as number) : 0;
  const pct = Math.round(prob * 100);
  const fontSize = hasProb ? 11 + prob * 3 : kind === "patient" ? 13 : 12;
  const borderWidth = hasProb ? 1.5 + prob * 2.5 : 2;

  return (
    <div
      className={`rounded-xl px-3 py-2 text-xs shadow-sm transition-shadow ${
        selected ? "shadow-lg ring-2 ring-blue-500 ring-offset-1" : ""
      } ${data.isNew ? "ring-2 ring-blue-400" : ""}`}
      style={{
        background: NODE_TINTS[kind],
        borderColor: NODE_COLORS[kind],
        borderStyle: "solid",
        borderWidth,
        color: NODE_TEXT_COLORS[kind],
        maxWidth: 240,
        fontSize,
        fontWeight: kind === "patient" || kind === "topic" ? 700 : 500,
      }}
    >
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <div className="flex items-center gap-2">
        <span>{data.label}</span>
        {hasProb && (
          <span
            className="ml-auto shrink-0 rounded-full bg-white/70 px-1.5 py-0.5 text-[10px] font-bold tabular-nums"
            style={{ color: NODE_COLORS[kind] }}
          >
            {pct}%
          </span>
        )}
      </div>
      {hasProb && (
        <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-white/60">
          <div
            className="h-full rounded-full"
            style={{ width: `${Math.max(3, pct)}%`, background: NODE_COLORS[kind] }}
          />
        </div>
      )}
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </div>
  );
}

const nodeTypes = { triage: TriageNode };

function nodeWidth(data: NodeData): number {
  const base = Math.max(120, Math.min(230, data.label.length * 6.6 + 40));
  if (data.kind === "condition" && typeof data.probability === "number") {
    return Math.min(252, base + Math.round(data.probability * 44));
  }
  return base;
}

function nodeHeight(data: NodeData): number {
  return data.kind === "condition" && typeof data.probability === "number" ? 58 : 46;
}

/** Left-to-right dagre layout, producing React Flow node positions. */
function layout(nodes: Node<NodeData>[], edges: Edge[]): Node<NodeData>[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 28, ranksep: 72, marginx: 24, marginy: 24 });
  nodes.forEach((n) => {
    g.setNode(n.id, { width: nodeWidth(n.data), height: nodeHeight(n.data) });
  });
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);
  return nodes.map((n) => {
    const p = g.node(n.id);
    return {
      ...n,
      position: { x: p.x - nodeWidth(n.data) / 2, y: p.y - nodeHeight(n.data) / 2 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    };
  });
}

function toReactFlow(graph: Graph | null): { nodes: Node<NodeData>[]; edges: Edge[] } {
  if (!graph) {
    // Seed a Patient node so the board is interactive before any analysis.
    return {
      nodes: layout(
        [
          {
            id: PATIENT_ID,
            type: "triage",
            position: { x: 0, y: 0 },
            data: { label: "Patient", kind: "patient", turn: 1 },
          },
        ],
        [],
      ),
      edges: [],
    };
  }

  const nodes: Node<NodeData>[] = graph.nodes.map((n) => ({
    id: n.data.id,
    type: "triage",
    position: { x: 0, y: 0 },
    data: {
      label: n.data.label,
      kind: n.data.kind,
      turn: n.data.turn,
      source: n.data.source,
      probability: n.data.probability,
      isNew: n.data.turn === graph.turns,
    },
  }));

  const edges: Edge[] = graph.edges.map((e) => {
    const escalates = e.data.relation === "escalates";
    return {
      id: e.data.id,
      source: e.data.source,
      target: e.data.target,
      label: e.data.relation,
      animated: escalates,
      markerEnd: { type: MarkerType.ArrowClosed, color: escalates ? "#ef4444" : "#94a3b8" },
      style: { stroke: escalates ? "#ef4444" : "#cbd5e1", strokeWidth: escalates ? 2 : 1.5 },
      labelStyle: { fontSize: 9, fill: "#94a3b8", fontWeight: 500 },
      labelBgStyle: { fill: "#ffffff", fillOpacity: 0.85 },
      labelBgPadding: [3, 1] as [number, number],
    };
  });

  return { nodes: layout(nodes, edges), edges };
}

interface SelectedNode {
  label: string;
  kind: NodeKind;
  turn: number;
  source: Provenance | null;
  probability?: number;
}

const FIT_OPTS = { padding: 0.25, maxZoom: 1.3, duration: 300 };

export default function ReasoningGraph() {
  const { state } = useConsultation();
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<NodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selected, setSelected] = useState<SelectedNode | null>(null);
  const [expanded, setExpanded] = useState(false);
  const rf = useRef<ReactFlowInstance<Node<NodeData>, Edge> | null>(null);

  // Rebuild + re-layout whenever the cumulative graph changes, then re-fit the
  // viewport so newly added nodes are always in view (fitView alone only fits
  // the initial render).
  useEffect(() => {
    const { nodes: n, edges: e } = toReactFlow(state.graph);
    setNodes(n);
    setEdges(e);
    const fitTimer = setTimeout(() => rf.current?.fitView(FIT_OPTS), 80);
    const newTimer = setTimeout(() => {
      setNodes((cur) =>
        cur.map((node) =>
          node.data.isNew ? { ...node, data: { ...node.data, isNew: false } } : node,
        ),
      );
    }, 4000);
    return () => {
      clearTimeout(fitTimer);
      clearTimeout(newTimer);
    };
  }, [state.graph, setNodes, setEdges]);

  // Re-fit when entering/leaving fullscreen (the canvas resizes).
  useEffect(() => {
    const t = setTimeout(() => rf.current?.fitView(FIT_OPTS), 140);
    return () => clearTimeout(t);
  }, [expanded]);

  const onNodeClick = useCallback((_: unknown, node: Node<NodeData>) => {
    setSelected({
      label: node.data.label,
      kind: node.data.kind,
      turn: node.data.turn,
      source: node.data.source ?? null,
      probability: node.data.probability,
    });
  }, []);

  // React Flow needs a DEFINITE height on the canvas container; min-h + flex
  // does not resolve, so we set an explicit height that also works fullscreen.
  const boardHeight = expanded ? "calc(100vh - 6rem)" : "min(68vh, 640px)";

  const board = (
    <div className={expanded ? "fixed inset-0 z-50 flex flex-col bg-white p-4" : "flex flex-col p-4 sm:p-5"}>
      <div
        className="relative w-full overflow-hidden rounded-xl ring-1 ring-slate-200"
        style={{ height: boardHeight }}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          onPaneClick={() => setSelected(null)}
          onInit={(inst) => {
            rf.current = inst;
            setTimeout(() => inst.fitView(FIT_OPTS), 60);
          }}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={FIT_OPTS}
          minZoom={0.2}
          maxZoom={2.5}
          proOptions={{ hideAttribution: false }}
        >
          <Background variant={BackgroundVariant.Dots} gap={22} size={1.4} color="#cbd5e1" />
          <Controls showInteractive={false} />
          <MiniMap
            pannable
            zoomable
            nodeColor={(n) => NODE_COLORS[(n.data as NodeData).kind] ?? "#94a3b8"}
            nodeStrokeWidth={2}
            className="!bg-white/80"
          />
        </ReactFlow>

        {/* Info + fullscreen, floating over the board. */}
        <div className="absolute left-3 top-3 z-10">
          <Tooltip
            side="bottom"
            label="Drag nodes to rearrange. Scroll or pinch to zoom. Tap any node to see its source."
          >
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-white/85 text-slate-400 shadow-sm ring-1 ring-slate-200 backdrop-blur hover:text-slate-600">
              <InfoIcon />
            </span>
          </Tooltip>
        </div>
        <button
          onClick={() => setExpanded((v) => !v)}
          title={expanded ? "Close fullscreen" : "Fullscreen"}
          className="absolute right-3 top-3 z-10 flex h-8 w-8 items-center justify-center rounded-lg bg-white/85 text-sm font-semibold text-slate-600 shadow-sm ring-1 ring-slate-200 backdrop-blur hover:text-slate-900"
        >
          {expanded ? "✕" : "⤢"}
        </button>

        {selected && (
          <aside className="absolute bottom-3 right-3 z-10 w-60 rounded-xl bg-white/95 p-3 text-xs shadow-lg ring-1 ring-slate-200 backdrop-blur">
            <p
              className="text-[10px] font-semibold uppercase tracking-wide"
              style={{ color: NODE_COLORS[selected.kind] }}
            >
              {NODE_KIND_LABELS[selected.kind]}
            </p>
            <p className="mt-0.5 text-sm font-semibold text-slate-800">{selected.label}</p>
            {typeof selected.probability === "number" && (
              <p className="mt-1 font-semibold text-slate-600">
                Estimated likelihood: {Math.round(selected.probability * 100)}%
              </p>
            )}
            <p className="mt-1 text-slate-500">First seen in recording #{selected.turn}</p>
            {selected.source ? (
              <div className="mt-2 border-t border-slate-100 pt-2">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                  Source
                </p>
                <div className="mt-1">
                  <SourceCitation source={selected.source} />
                </div>
              </div>
            ) : null}
          </aside>
        )}
      </div>

      <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1.5">
        {KIND_ORDER.map((kind) => (
          <span key={kind} className="inline-flex items-center gap-1.5 text-xs text-slate-500">
            <span
              className="h-2.5 w-2.5 rounded-sm ring-1"
              style={{ backgroundColor: NODE_TINTS[kind], borderColor: NODE_COLORS[kind] }}
            />
            {NODE_KIND_LABELS[kind]}
          </span>
        ))}
      </div>
    </div>
  );

  // Fullscreen renders through a portal to document.body so it escapes any
  // transformed ancestor (which would otherwise trap position: fixed).
  return expanded ? createPortal(board, document.body) : board;
}
