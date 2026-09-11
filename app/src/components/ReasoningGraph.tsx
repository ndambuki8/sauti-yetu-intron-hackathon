import { useMemo, useState } from "react";
import { StyleSheet, Text, View, useWindowDimensions } from "react-native";
import Svg, { G, Line, Rect, Text as SvgText } from "react-native-svg";
import type { Graph } from "../api/types";
import { NODE_COLORS, NODE_KIND_LABELS, NODE_TINTS, type NodeKind } from "../lib/palette";
import { colors, fonts } from "../theme";

const COLUMNS: NodeKind[][] = [
  ["patient"],
  ["symptom", "finding"],
  ["topic", "red_flag"],
  ["condition"],
  ["department"],
];

const NODE_W = 132;
const NODE_H = 42;
const COL_GAP = 28;
const ROW_GAP = 16;

export function ReasoningGraph({ graph }: { graph: Graph | null }) {
  const { width } = useWindowDimensions();
  const [selected, setSelected] = useState<string | null>(null);

  const layout = useMemo(() => {
    if (!graph?.nodes.length) return null;
    const byKind = new Map<string, typeof graph.nodes>();
    for (const node of graph.nodes) {
      const kind = node.data.kind;
      const list = byKind.get(kind) ?? [];
      list.push(node);
      byKind.set(kind, list);
    }
    const positions = new Map<string, { x: number; y: number; node: (typeof graph.nodes)[0] }>();
    COLUMNS.forEach((kinds, col) => {
      const nodes = kinds.flatMap((k) => byKind.get(k) ?? []);
      nodes.forEach((node, row) => {
        positions.set(node.data.id, {
          x: 16 + col * (NODE_W + COL_GAP),
          y: 16 + row * (NODE_H + ROW_GAP),
          node,
        });
      });
    });
    const maxRow = Math.max(
      1,
      ...COLUMNS.map((kinds) => kinds.flatMap((k) => byKind.get(k) ?? []).length),
    );
    return {
      positions,
      width: 16 * 2 + COLUMNS.length * NODE_W + (COLUMNS.length - 1) * COL_GAP,
      height: 16 * 2 + maxRow * NODE_H + (maxRow - 1) * ROW_GAP,
    };
  }, [graph]);

  if (!graph?.nodes.length || !layout) {
    return (
      <View style={styles.empty}>
        <Text style={styles.emptyTitle}>The picture is still empty</Text>
        <Text style={styles.emptyBody}>
          Record the patient. Symptoms, topics, and probable conditions will gather here.
        </Text>
      </View>
    );
  }

  const selectedNode = selected ? layout.positions.get(selected)?.node : undefined;
  const canvasW = Math.max(layout.width, width - 32);

  return (
    <View style={styles.wrap}>
      <Svg width={canvasW} height={layout.height}>
        {graph.edges.map((edge) => {
          const a = layout.positions.get(edge.data.source);
          const b = layout.positions.get(edge.data.target);
          if (!a || !b) return null;
          return (
            <Line
              key={edge.data.id}
              x1={a.x + NODE_W}
              y1={a.y + NODE_H / 2}
              x2={b.x}
              y2={b.y + NODE_H / 2}
              stroke={colors.line}
              strokeWidth={1.5}
            />
          );
        })}
        {Array.from(layout.positions.values()).map(({ x, y, node }) => {
          const kind = node.data.kind;
          const on = selected === node.data.id;
          return (
            <G
              key={node.data.id}
              onPress={() => setSelected(node.data.id)}
            >
              <Rect
                x={x}
                y={y}
                width={NODE_W}
                height={NODE_H}
                fill={NODE_TINTS[kind]}
                stroke={on ? NODE_COLORS[kind] : colors.line}
                strokeWidth={on ? 2 : 1}
              />
              <SvgText
                x={x + 8}
                y={y + 16}
                fill={NODE_COLORS[kind]}
                fontSize={9}
                fontFamily={fonts.bodyMed}
              >
                {NODE_KIND_LABELS[kind]}
              </SvgText>
              <SvgText
                x={x + 8}
                y={y + 32}
                fill={colors.ink}
                fontSize={11}
                fontFamily={fonts.body}
              >
                {node.data.label.length > 18 ? `${node.data.label.slice(0, 17)}…` : node.data.label}
              </SvgText>
            </G>
          );
        })}
      </Svg>
      {selectedNode ? (
        <View style={styles.inspector}>
          <Text style={styles.inspKind}>{NODE_KIND_LABELS[selectedNode.data.kind]}</Text>
          <Text style={styles.inspLabel}>{selectedNode.data.label}</Text>
          <Text style={styles.inspTurn}>First heard on turn {selectedNode.data.turn}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 12 },
  empty: { paddingVertical: 28, gap: 8 },
  emptyTitle: { fontFamily: fonts.displaySemi, fontSize: 22, color: colors.ink },
  emptyBody: { fontFamily: fonts.body, fontSize: 15, color: colors.muted, lineHeight: 22 },
  inspector: {
    padding: 12,
    backgroundColor: colors.paper,
    borderWidth: 1,
    borderColor: colors.line,
    gap: 4,
  },
  inspKind: {
    fontFamily: fonts.bodyMed,
    fontSize: 11,
    letterSpacing: 0.8,
    textTransform: "uppercase",
    color: colors.celadon,
  },
  inspLabel: { fontFamily: fonts.bodySemi, fontSize: 16, color: colors.ink },
  inspTurn: { fontFamily: fonts.body, fontSize: 13, color: colors.muted },
});
