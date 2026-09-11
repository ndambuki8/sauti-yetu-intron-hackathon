export type FlowShape = "rect" | "diamond" | "round";

export interface FlowNode {
  id: string;
  label: string;
  shape: FlowShape;
}

export interface FlowEdge {
  source: string;
  target: string;
  label?: string;
}

export interface FlowChartModel {
  direction: "TD" | "LR";
  nodes: FlowNode[];
  edges: FlowEdge[];
}

const NODE_TOKEN =
  /^([A-Za-z][\w]*)\s*(?:\[([^\]]*)\]|\{([^}]*)\}|\(\(([^)]*)\)\)|\(([^)]*)\))?/;

function shapeFromMatch(m: RegExpMatchArray): { label?: string; shape: FlowShape } {
  if (m[2] != null) return { label: m[2], shape: "rect" };
  if (m[3] != null) return { label: m[3], shape: "diamond" };
  if (m[4] != null || m[5] != null) return { label: m[4] ?? m[5], shape: "round" };
  return { shape: "rect" };
}

function parseNodeToken(raw: string): FlowNode | null {
  const text = raw.trim();
  if (!text) return null;
  const m = text.match(NODE_TOKEN);
  if (!m) return null;
  const { label, shape } = shapeFromMatch(m);
  return { id: m[1], label: (label ?? m[1]).trim(), shape };
}

function stripFence(body: string): string {
  const fenced = body.match(/```(?:mermaid)?\s*([\s\S]*?)```/i);
  return (fenced?.[1] ?? body).trim();
}

export function looksLikeMermaid(body: string): boolean {
  const src = stripFence(body);
  return /^(flowchart|graph)\s+(TD|TB|LR|RL|BT)\b/im.test(src);
}

export function parseMermaidFlow(body: string): FlowChartModel | null {
  const src = stripFence(body);
  if (!/^(flowchart|graph)\s+/im.test(src)) return null;

  const nodes = new Map<string, FlowNode>();
  const edges: FlowEdge[] = [];
  let direction: "TD" | "LR" = "TD";

  const upsert = (node: FlowNode | null) => {
    if (!node) return;
    const prev = nodes.get(node.id);
    if (!prev || (node.label && node.label !== node.id)) nodes.set(node.id, node);
    else if (!prev) nodes.set(node.id, node);
  };

  for (const rawLine of src.split(/\n/)) {
    const line = rawLine.replace(/%%.*$/, "").trim();
    if (!line || line === "end" || /^subgraph\b/i.test(line)) continue;

    const header = line.match(/^(?:flowchart|graph)\s+(TD|TB|LR|RL|BT)\b/i);
    if (header) {
      const dir = header[1].toUpperCase();
      direction = dir === "LR" || dir === "RL" ? "LR" : "TD";
      continue;
    }

    const edge = line.match(/^(.*?)\s*-->\s*(?:\|([^|]+)\|)?\s*(.+)$/);
    if (edge) {
      const source = parseNodeToken(edge[1]);
      const target = parseNodeToken(edge[3]);
      upsert(source);
      upsert(target);
      if (source && target) {
        const label = edge[2]?.trim();
        edges.push({ source: source.id, target: target.id, label: label || undefined });
      }
      continue;
    }

    upsert(parseNodeToken(line));
  }

  if (!nodes.size) return null;
  return { direction, nodes: Array.from(nodes.values()), edges };
}

export function wrapLabel(label: string, max = 26): string[] {
  const words = label.replace(/\s+/g, " ").trim().split(" ");
  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length > max && current) {
      lines.push(current);
      current = word;
    } else {
      current = next;
    }
  }
  if (current) lines.push(current);
  return lines.slice(0, 5);
}
