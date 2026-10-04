"use client";

/**
 * Engineering Lab — organization chart visualization (B3-a).
 *
 * Pure SVG rendering of an OrganizationSpec with per-topology layouts:
 * single (centered), pipeline (horizontal chain), hierarchical (root top,
 * children below), hub-and-spoke (hub center, spokes on a circle). Nodes are
 * resolved through the catalog lookups (body name, occupancy model, tool
 * count). Edges are clipped at node boundaries with arrowheads; kind styling:
 * delegation = solid neutral, review = dashed amber, handoff = dotted emerald.
 *
 * Accessibility: the SVG carries role="img" + a descriptive aria-label, and a
 * visually-hidden list mirrors nodes/edges for screen readers.
 */

import type { OrganizationSpec, OrgEdge, OrgNode } from "@/lib/lab/contracts";
import type { CatalogLookups } from "./lab-api";
import { truncate } from "./format";
import { TopologyBadge } from "./badges";

interface Pt {
  x: number;
  y: number;
}

const NODE_W = 170;
const NODE_H = 78;
const PAD = 20;

const EDGE_STYLES: Record<
  OrgEdge["kind"],
  { stroke: string; dash?: string; label: string; legend: string }
> = {
  delegation: { stroke: "#a3a3a3", label: "delegation", legend: "border-solid border-neutral-400" },
  review: { stroke: "#fbbf24", dash: "6 4", label: "review", legend: "border-dashed border-amber-400" },
  handoff: { stroke: "#34d399", dash: "2 5", label: "handoff", legend: "border-dotted border-emerald-400" },
};

export interface OrgChartProps {
  organization: OrganizationSpec;
  occupancy: { nodeId: string; modelId: string }[];
  capabilities: { nodeId: string; toolIds: string[] }[];
  lookups: CatalogLookups;
}

function center(pos: Pt): Pt {
  return { x: pos.x + NODE_W / 2, y: pos.y + NODE_H / 2 };
}

/** Center-to-center, clipped at both node rectangles (same size). */
function edgePoints(a: Pt, b: Pt, pad = 8): [Pt, Pt] {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  const ux = dx / len;
  const uy = dy / len;
  const exit = Math.min(
    NODE_W / 2 / (Math.abs(ux) < 1e-9 ? Infinity : Math.abs(ux)),
    NODE_H / 2 / (Math.abs(uy) < 1e-9 ? Infinity : Math.abs(uy)),
  );
  const trim = Math.min(exit + pad, len / 2);
  return [
    { x: a.x + ux * trim, y: a.y + uy * trim },
    { x: b.x - ux * trim, y: b.y - uy * trim },
  ];
}

function layout(org: OrganizationSpec): { width: number; height: number; positions: Map<string, Pt> } {
  const positions = new Map<string, Pt>();
  const n = org.nodes.length;
  switch (org.topology) {
    case "single": {
      const width = Math.max(260, NODE_W + 2 * PAD);
      const height = NODE_H + 2 * PAD;
      positions.set(org.nodes[0].id, { x: (width - NODE_W) / 2, y: (height - NODE_H) / 2 });
      return { width, height, positions };
    }
    case "pipeline": {
      const gap = 64;
      const width = Math.max(340, n * NODE_W + (n - 1) * gap + 2 * PAD);
      const height = NODE_H + 2 * PAD;
      org.nodes.forEach((node, i) => {
        positions.set(node.id, { x: PAD + i * (NODE_W + gap), y: PAD });
      });
      return { width, height, positions };
    }
    case "hierarchical": {
      const root = org.nodes.find((node) => !node.reportsTo) ?? org.nodes[0];
      const children = org.nodes.filter((node) => node.id !== root.id);
      const gap = 48;
      const childrenWidth = children.length * NODE_W + Math.max(0, children.length - 1) * gap;
      const width = Math.max(340, Math.max(NODE_W, childrenWidth) + 2 * PAD);
      positions.set(root.id, { x: (width - NODE_W) / 2, y: PAD });
      const childY = PAD + NODE_H + 92;
      const startX = (width - childrenWidth) / 2;
      children.forEach((node, i) => {
        positions.set(node.id, { x: startX + i * (NODE_W + gap), y: childY });
      });
      return { width, height: childY + NODE_H + PAD, positions };
    }
    case "hub-and-spoke": {
      const hub = org.nodes[0];
      const spokes = org.nodes.slice(1);
      const r = 118;
      const width = Math.max(380, 2 * (r + NODE_W / 2) + 2 * PAD);
      const height = 2 * (r + NODE_H / 2) + 2 * PAD;
      const cx = width / 2;
      const cy = height / 2;
      positions.set(hub.id, { x: cx - NODE_W / 2, y: cy - NODE_H / 2 });
      spokes.forEach((node, i) => {
        const angle = ((-90 + (i * 360) / spokes.length) * Math.PI) / 180;
        positions.set(node.id, {
          x: cx + r * Math.cos(angle) - NODE_W / 2,
          y: cy + r * Math.sin(angle) - NODE_H / 2,
        });
      });
      return { width, height, positions };
    }
  }
}

export function OrgChart({ organization, occupancy, capabilities, lookups }: OrgChartProps) {
  const { width, height, positions } = layout(organization);
  const markerPrefix = `mc-${organization.id.replace(/[^a-zA-Z0-9]/g, "")}`;
  const rootIds = new Set(organization.nodes.filter((n) => !n.reportsTo).map((n) => n.id));

  const bodyName = (node: OrgNode): string =>
    lookups.bodies.get(node.bodyId)?.name ?? node.bodyId;
  const modelName = (nodeId: string): string => {
    const entry = occupancy.find((o) => o.nodeId === nodeId);
    return entry ? (lookups.models.get(entry.modelId)?.name ?? entry.modelId) : "model unassigned";
  };
  const toolCount = (nodeId: string): number =>
    capabilities.find((c) => c.nodeId === nodeId)?.toolIds.length ?? 0;

  const nodeById = new Map(organization.nodes.map((n) => [n.id, n]));
  const ariaLabel =
    `${organization.nodes.length}-node ${organization.topology} organization: ` +
    `${organization.nodes.map((n) => `${bodyName(n)} as ${n.role}`).join(", ")}. ` +
    (organization.edges.length > 0
      ? `Edges: ${organization.edges
          .map((e) => {
            const from = nodeById.get(e.from);
            const to = nodeById.get(e.to);
            return `${from ? bodyName(from) : e.from} ${EDGE_STYLES[e.kind].label}s to ${to ? bodyName(to) : e.to}`;
          })
          .join("; ")}.`
      : "No edges.");

  return (
    <figure className="m-0">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-neutral-200">{organization.name}</span>
        <TopologyBadge topology={organization.topology} />
        <span className="font-mono text-[10px] text-neutral-600">
          {organization.nodes.length} nodes · {organization.edges.length} edges
        </span>
      </div>
      <div className="overflow-x-auto rounded-lg border border-neutral-800 bg-neutral-950/60 p-2">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={ariaLabel}
          className="h-auto w-full min-w-[480px] max-w-full"
        >
          <defs>
            {(Object.keys(EDGE_STYLES) as OrgEdge["kind"][]).map((kind) => (
              <marker
                key={kind}
                id={`${markerPrefix}-${kind}`}
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="7"
                markerHeight="7"
                orient="auto-start-reverse"
              >
                <path d="M 0 1 L 9 5 L 0 9 z" fill={EDGE_STYLES[kind].stroke} />
              </marker>
            ))}
          </defs>
          {organization.edges.map((edge) => {
            const from = positions.get(edge.from);
            const to = positions.get(edge.to);
            if (!from || !to) return null;
            const [a, b] = edgePoints(center(from), center(to));
            const style = EDGE_STYLES[edge.kind];
            return (
              <line
                key={`${edge.from}-${edge.to}-${edge.kind}`}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={style.stroke}
                strokeWidth={1.5}
                strokeDasharray={style.dash}
                strokeLinecap="round"
                markerEnd={`url(#${markerPrefix}-${edge.kind})`}
              />
            );
          })}
          {organization.nodes.map((node) => {
            const pos = positions.get(node.id);
            if (!pos) return null;
            const isLead = rootIds.has(node.id) || organization.nodes[0].id === node.id;
            const stroke = isLead ? "#10b981" : "#404040";
            const nameFill = isLead ? "#6ee7b7" : "#f5f5f5";
            return (
              <g key={node.id} transform={`translate(${pos.x},${pos.y})`}>
                <rect
                  width={NODE_W}
                  height={NODE_H}
                  rx={9}
                  fill="#171717"
                  stroke={stroke}
                  strokeWidth={isLead ? 1.6 : 1}
                />
                <text x={12} y={23} fontSize={12} fontWeight={600} fill={nameFill}>
                  {truncate(bodyName(node))}
                </text>
                <text x={12} y={39} fontSize={10.5} fill="#a3a3a3">
                  {truncate(node.role, 26)}
                </text>
                <text x={12} y={54} fontSize={10} fill="#6ee7b7">
                  {truncate(modelName(node.id), 26)}
                </text>
                <text x={12} y={68} fontSize={9.5} fill="#737373">
                  {toolCount(node.id)} tool{toolCount(node.id) === 1 ? "" : "s"} allocated
                </text>
              </g>
            );
          })}
        </svg>
        {/* Screen-reader mirror of the chart content. */}
        <div className="sr-only">
          <ol>
            {organization.nodes.map((node) => (
              <li key={node.id}>{`${bodyName(node)} — role: ${node.role}, ${modelName(node.id)}, ${toolCount(node.id)} tools`}</li>
            ))}
          </ol>
          <ul>
            {organization.edges.map((edge) => {
              const from = nodeById.get(edge.from);
              const to = nodeById.get(edge.to);
              return (
                <li key={`${edge.from}-${edge.to}-${edge.kind}`}>
                  {`${from ? bodyName(from) : edge.from} ${EDGE_STYLES[edge.kind].label} ${to ? bodyName(to) : edge.to}`}
                </li>
              );
            })}
          </ul>
        </div>
      </div>
      <figcaption className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5 px-1 text-[10px] text-neutral-500">
        {(Object.keys(EDGE_STYLES) as OrgEdge["kind"][]).map((kind) => (
          <span key={kind} className="inline-flex items-center gap-1.5">
            <span className={`h-0 w-5 border-t-2 ${EDGE_STYLES[kind].legend}`} aria-hidden="true" />
            {EDGE_STYLES[kind].label}
          </span>
        ))}
        <span className="text-neutral-600">lead / root nodes highlighted emerald</span>
      </figcaption>
    </figure>
  );
}
