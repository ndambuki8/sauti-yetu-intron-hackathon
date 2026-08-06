import cytoscape from "cytoscape";
import { useEffect, useRef, useState } from "react";
import type { Graph, GraphNode } from "../api/types";
import {
  NODE_COLORS,
  NODE_KIND_LABELS,
  NODE_TEXT_COLORS,
  NODE_TINTS,
  type NodeKind,
} from "../lib/palette";
import { useConsultation } from "../state/consultation";

const KIND_ORDER: NodeKind[] = [
  "symptom",
  "finding",
  "condition",
  "red_flag",
  "topic",
  "department",
];

/**
 * Miro-style compact pills: the label lives inside a tinted round-rectangle,
 * sized to the text. Keeps information density high without giant circles.
 */
function buildStylesheet(): cytoscape.StylesheetStyle[] {
  const kindStyles = (Object.keys(NODE_COLORS) as NodeKind[]).map((kind) => ({
    selector: `node[kind="${kind}"]`,
    style: {
      "background-color": NODE_TINTS[kind],
      "border-color": NODE_COLORS[kind],
      color: NODE_TEXT_COLORS[kind],
      ...(kind === "patient" ? { "font-weight": 700, "font-size": 12 } : {}),
      ...(kind === "red_flag" ? { "border-width": 2, "font-weight": 600 } : {}),
      ...(kind === "topic" ? { "font-weight": 600 } : {}),
    },
  }));

  return [
    {
      selector: "node",
      style: {
        label: "data(label)",
        shape: "round-rectangle",
        width: "label",
        height: "label",
        padding: "10px",
        "font-size": 11,
        "font-family": "Inter, sans-serif",
        "text-valign": "center",
        "text-halign": "center",
        "text-wrap": "wrap",
        "text-max-width": "150px",
        "border-width": 1.5,
      },
    },
    ...kindStyles,
    {
      selector: "edge",
      style: {
        width: 1.25,
        "line-color": "#c3ccd6",
        "target-arrow-color": "#c3ccd6",
        "target-arrow-shape": "triangle",
        "arrow-scale": 0.8,
        // Right-angle connectors, horizontal flow — the Miro/fishbone look.
        "curve-style": "taxi",
        "taxi-direction": "horizontal",
        "taxi-turn": 24,
      },
    },
    {
      selector: 'edge[relation="escalates"]',
      style: {
        "line-color": "#b3271e",
        "target-arrow-color": "#b3271e",
        width: 2,
        "line-style": "dashed",
      },
    },
    {
      selector: "node.new",
      style: { "border-color": "#1d4ed8", "border-width": 2.5 },
    },
    {
      selector: ".faded",
      style: { opacity: 0.15 },
    },
    {
      selector: "node.selected",
      style: { "border-color": "#1d4ed8", "border-width": 2.5 },
    },
  ];
}

/** Deterministic layered flow: patient on the left, then symptoms/findings,
 * topic, conditions/department — levels spread left-to-right, so the graph
 * reads like a clinical reasoning chain instead of a force-directed cloud. */
function runLayout(cy: cytoscape.Core) {
  cy.layout({
    name: "breadthfirst",
    directed: true,
    padding: 32,
    spacingFactor: 1.05,
    animate: true,
    animationDuration: 450,
    fit: true,
    // breadthfirst lays out top-down; swap axes for a left-to-right flow.
    transform: (_node, pos) => ({ x: pos.y, y: pos.x }),
  } as cytoscape.LayoutOptions).run();
}

interface SelectedNode {
  label: string;
  kind: NodeKind;
  turn: number;
  relations: string[];
}

export default function ReasoningGraph() {
  const { state } = useConsultation();
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const [selected, setSelected] = useState<SelectedNode | null>(null);
  const [initFailed, setInitFailed] = useState(false);

  // Initialise Cytoscape once.
  useEffect(() => {
    if (!containerRef.current) return;
    try {
      const cy = cytoscape({
        container: containerRef.current,
        elements: [],
        style: buildStylesheet(),
        wheelSensitivity: 0.2,
        minZoom: 0.25,
        maxZoom: 2.5,
      });

      cy.on("tap", "node", (event) => {
        const node = event.target as cytoscape.NodeSingular;
        const data = node.data() as GraphNode["data"];
        cy.elements().addClass("faded");
        node.closedNeighborhood().removeClass("faded");
        cy.nodes().removeClass("selected");
        node.addClass("selected");
        setSelected({
          label: data.label,
          kind: data.kind,
          turn: data.turn,
          relations: [
            ...new Set(node.connectedEdges().map((e) => e.data("relation") as string)),
          ],
        });
      });

      cy.on("tap", (event) => {
        if (event.target === cy) {
          cy.elements().removeClass("faded");
          cy.nodes().removeClass("selected");
          setSelected(null);
        }
      });

      cyRef.current = cy;
      return () => {
        cy.destroy();
        cyRef.current = null;
      };
    } catch (err) {
      console.error("Cytoscape failed to initialise", err);
      setInitFailed(true);
    }
  }, []);

  // Merge the cumulative graph whenever it changes.
  useEffect(() => {
    const cy = cyRef.current;
    const graph: Graph | null = state.graph;
    if (!cy || !graph) return;

    cy.nodes().removeClass("new");
    for (const el of [...graph.nodes, ...graph.edges]) {
      if (cy.getElementById(el.data.id).empty()) {
        const added = cy.add(el as cytoscape.ElementDefinition);
        if (el.data.turn === graph.turns) added.addClass("new");
      }
    }

    runLayout(cy);

    const timer = setTimeout(() => cy.nodes().removeClass("new"), 4000);
    return () => clearTimeout(timer);
  }, [state.graph]);

  // Clear on consultation reset.
  useEffect(() => {
    if (!state.sessionId && cyRef.current) {
      cyRef.current.elements().remove();
      setSelected(null);
    }
  }, [state.sessionId]);

  const zoomBy = (factor: number) => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.zoom({
      level: cy.zoom() * factor,
      renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 },
    });
  };

  return (
    <section className="card flex min-h-[560px] flex-col p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="card-title">Clinical reasoning graph</h2>
          <p className="mt-1 text-xs text-slate-400">
            Built from Intron Sahara extractions · grows left to right with each
            recording · newest additions outlined in blue · click a node to inspect it
          </p>
        </div>
        <div className="flex shrink-0 gap-1 rounded-lg bg-slate-100 p-1">
          <button
            onClick={() => zoomBy(0.8)}
            className="rounded-md px-2.5 py-1 text-sm font-semibold text-slate-600 hover:bg-white hover:shadow-sm"
            title="Zoom out"
          >
            −
          </button>
          <button
            onClick={() => cyRef.current?.fit(undefined, 32)}
            className="rounded-md px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-white hover:shadow-sm"
            title="Fit view"
          >
            Fit
          </button>
          <button
            onClick={() => zoomBy(1.25)}
            className="rounded-md px-2.5 py-1 text-sm font-semibold text-slate-600 hover:bg-white hover:shadow-sm"
            title="Zoom in"
          >
            +
          </button>
        </div>
      </div>

      <div className="relative mt-4 flex-1 rounded-lg bg-slate-50 ring-1 ring-slate-200">
        {initFailed ? (
          <p className="p-6 text-sm text-slate-500">
            The graph renderer failed to load. The triage cards and timeline
            still carry the full clinical picture.
          </p>
        ) : (
          <div ref={containerRef} className="graph-canvas rounded-lg" />
        )}

        {!state.graph && !initFailed && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <div className="max-w-sm text-center">
              <p className="text-sm font-medium text-slate-500">
                The patient's clinical picture will map out here
              </p>
              <p className="mt-1 text-xs text-slate-400">
                Patient → symptoms and findings → triage topic → possible
                conditions and routing, building up as the conversation is analysed.
              </p>
            </div>
          </div>
        )}

        {selected && (
          <aside className="absolute right-3 top-3 w-60 rounded-lg bg-white p-3 text-xs shadow-lg ring-1 ring-slate-200">
            <p
              className="text-[10px] font-semibold uppercase tracking-wide"
              style={{ color: NODE_COLORS[selected.kind] }}
            >
              {NODE_KIND_LABELS[selected.kind]}
            </p>
            <p className="mt-0.5 text-sm font-semibold text-slate-800">{selected.label}</p>
            <p className="mt-1 text-slate-500">
              First mentioned in recording #{selected.turn}
            </p>
            {selected.relations.length > 0 && (
              <p className="mt-1 text-slate-500">
                Relationships: {selected.relations.join(", ")}
              </p>
            )}
          </aside>
        )}
      </div>

      <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1.5">
        {KIND_ORDER.map((kind) => (
          <span key={kind} className="inline-flex items-center gap-1.5 text-xs text-slate-500">
            <span
              className="h-2.5 w-2.5 rounded-sm ring-1"
              style={{
                backgroundColor: NODE_TINTS[kind],
                borderColor: NODE_COLORS[kind],
              }}
            />
            {NODE_KIND_LABELS[kind]}
          </span>
        ))}
      </div>
    </section>
  );
}
