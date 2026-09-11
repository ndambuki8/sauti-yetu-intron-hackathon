import { Fragment, useMemo } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import Svg, { Line, Polygon, Rect, Text as SvgText } from "react-native-svg";
import { parseMermaidFlow, wrapLabel, type FlowNode } from "../lib/mermaid";
import { colors, fonts } from "../theme";

const NODE_W = 168;
const LINE_H = 14;
const PAD_Y = 10;
const COL_GAP = 36;
const ROW_GAP = 48;

function tone(label: string): { fill: string; stroke: string } {
  const t = label.toLowerCase();
  if (/red flag|emergency|immediate|stab|bleed|unconscious/.test(t)) {
    return { fill: "#FBECEA", stroke: colors.blood };
  }
  if (/question|clarif|how |has |is the/.test(t)) {
    return { fill: "#E6F2EE", stroke: colors.celadon };
  }
  if (/possible|migraine|headache|glaucoma|stroke|infection|sinus|tension|cluster/.test(t)) {
    return { fill: "#FBF3E0", stroke: colors.amber };
  }
  return { fill: colors.paper, stroke: colors.cedar };
}

function nodeHeight(node: FlowNode): number {
  const lines = wrapLabel(node.label);
  const textH = Math.max(1, lines.length) * LINE_H + PAD_Y * 2;
  return node.shape === "diamond" ? textH + 18 : textH;
}

function ranks(model: NonNullable<ReturnType<typeof parseMermaidFlow>>): Map<string, number> {
  const rank = new Map<string, number>();
  const outgoing = new Map<string, string[]>();
  const incoming = new Map<string, number>();
  for (const n of model.nodes) incoming.set(n.id, 0);
  for (const e of model.edges) {
    outgoing.set(e.source, [...(outgoing.get(e.source) ?? []), e.target]);
    incoming.set(e.target, (incoming.get(e.target) ?? 0) + 1);
  }
  const queue = model.nodes.filter((n) => !incoming.get(n.id)).map((n) => n.id);
  if (!queue.length && model.nodes[0]) queue.push(model.nodes[0].id);
  for (const id of queue) rank.set(id, 0);
  let steps = 0;
  while (queue.length && steps < 400) {
    steps += 1;
    const id = queue.shift() as string;
    const nextRank = (rank.get(id) ?? 0) + 1;
    for (const child of outgoing.get(id) ?? []) {
      const current = rank.get(child) ?? -1;
      if (nextRank > current) {
        rank.set(child, nextRank);
        queue.push(child);
      }
    }
  }
  for (const n of model.nodes) {
    if (!rank.has(n.id)) rank.set(n.id, 0);
  }
  return rank;
}

export function Flowchart({ source }: { source: string }) {
  const laid = useMemo(() => {
    const model = parseMermaidFlow(source);
    if (!model) return null;
    const rank = ranks(model);
    const byRank = new Map<number, FlowNode[]>();
    for (const node of model.nodes) {
      const r = rank.get(node.id) ?? 0;
      byRank.set(r, [...(byRank.get(r) ?? []), node]);
    }
    const positions = new Map<string, { x: number; y: number; w: number; h: number; node: FlowNode }>();
    const vertical = model.direction === "TD";
    let maxX = 0;
    let maxY = 0;

    if (vertical) {
      const orderedRanks = [...byRank.keys()].sort((a, b) => a - b);
      let y = 16;
      for (const r of orderedRanks) {
        const row = byRank.get(r) ?? [];
        const heights = row.map(nodeHeight);
        const rowH = Math.max(...heights, 36);
        row.forEach((node, i) => {
          const h = heights[i];
          const x = 16 + i * (NODE_W + COL_GAP);
          positions.set(node.id, { x, y: y + (rowH - h) / 2, w: NODE_W, h, node });
          maxX = Math.max(maxX, x + NODE_W);
        });
        y += rowH + ROW_GAP;
      }
      maxY = y;
    } else {
      const orderedRanks = [...byRank.keys()].sort((a, b) => a - b);
      let x = 16;
      for (const r of orderedRanks) {
        const col = byRank.get(r) ?? [];
        col.forEach((node, i) => {
          const h = nodeHeight(node);
          const py = 16 + i * (h + 20);
          positions.set(node.id, { x, y: py, w: NODE_W, h, node });
          maxY = Math.max(maxY, py + h);
        });
        x += NODE_W + COL_GAP + 24;
      }
      maxX = x;
    }

    return { model, positions, width: maxX + 24, height: maxY + 16, vertical };
  }, [source]);

  if (!laid) {
    return <Text style={styles.fallback}>{source}</Text>;
  }

  return (
    <View style={styles.wrap}>
      <ScrollView horizontal showsHorizontalScrollIndicator>
        <Svg width={laid.width} height={laid.height}>
          {laid.model.edges.map((edge, i) => {
            const a = laid.positions.get(edge.source);
            const b = laid.positions.get(edge.target);
            if (!a || !b) return null;
            const x1 = laid.vertical ? a.x + a.w / 2 : a.x + a.w;
            const y1 = laid.vertical ? a.y + a.h : a.y + a.h / 2;
            const x2 = laid.vertical ? b.x + b.w / 2 : b.x;
            const y2 = laid.vertical ? b.y : b.y + b.h / 2;
            return (
              <Line
                key={`${edge.source}-${edge.target}-${i}`}
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke={colors.cedar}
                strokeWidth={1.4}
              />
            );
          })}
          {laid.model.edges.map((edge, i) => {
            if (!edge.label) return null;
            const a = laid.positions.get(edge.source);
            const b = laid.positions.get(edge.target);
            if (!a || !b) return null;
            const x = laid.vertical ? (a.x + a.w / 2 + b.x + b.w / 2) / 2 : (a.x + a.w + b.x) / 2;
            const y = laid.vertical ? (a.y + a.h + b.y) / 2 : a.y + a.h / 2 - 8;
            return (
              <SvgText
                key={`lbl-${i}`}
                x={x}
                y={y}
                fill={colors.emberDeep}
                fontSize={9}
                textAnchor="middle"
              >
                {edge.label.length > 28 ? `${edge.label.slice(0, 27)}…` : edge.label}
              </SvgText>
            );
          })}
          {Array.from(laid.positions.values()).map(({ x, y, w, h, node }) => {
            const { fill, stroke } = tone(node.label);
            const lines = wrapLabel(node.label);
            const cx = x + w / 2;
            const cy = y + h / 2;
            return (
              <Fragment key={node.id}>
                {node.shape === "diamond" ? (
                  <Polygon
                    points={`${cx},${y} ${x + w},${cy} ${cx},${y + h} ${x},${cy}`}
                    fill={fill}
                    stroke={stroke}
                    strokeWidth={1.5}
                  />
                ) : (
                  <Rect
                    x={x}
                    y={y}
                    width={w}
                    height={h}
                    rx={node.shape === "round" ? 16 : 4}
                    fill={fill}
                    stroke={stroke}
                    strokeWidth={1.5}
                  />
                )}
                {lines.map((line, li) => (
                  <SvgText
                    key={li}
                    x={cx}
                    y={cy - ((lines.length - 1) * LINE_H) / 2 + li * LINE_H + 4}
                    fill={colors.ink}
                    fontSize={10}
                    textAnchor="middle"
                  >
                    {line}
                  </SvgText>
                ))}
              </Fragment>
            );
          })}
        </Svg>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: "#F7F4EE",
    paddingVertical: 8,
  },
  fallback: { fontFamily: fonts.body, fontSize: 14, color: colors.ink, lineHeight: 21 },
});
