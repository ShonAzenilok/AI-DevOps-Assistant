import { useMemo } from 'react'
import { Background, BackgroundVariant, Handle, Position, ReactFlow } from '@xyflow/react'
import type { Edge, Node, NodeProps } from '@xyflow/react'
import type { AwsResourceType, GroupKind, ScanResult } from '../../types'
import { ResourceIcon } from '../icons'

type AwsNodeData = {
  label: string
  sublabel: string
  resourceType: AwsResourceType
}

type AwsGroupData = {
  label: string
  color: string
  kind?: GroupKind
}

type AwsFlowNode = Node<AwsNodeData, 'aws'>
type AwsGroupNode = Node<AwsGroupData, 'awsGroup'>

function AwsNode({ data }: NodeProps<AwsFlowNode>) {
  return (
    <div className="aws-node">
      <Handle type="target" position={Position.Top} />
      <div className="aws-node__glyph">
        <ResourceIcon type={data.resourceType} />
      </div>
      <div className="aws-node__label">{data.label}</div>
      <div className="aws-node__sub">{data.sublabel}</div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  )
}

// AWS architecture-diagram container conventions (documentation style):
// dashed teal region, solid purple VPC, solid neutral AWS-cloud/global box.
const GROUP_FALLBACK_COLORS: Record<string, string> = {
  region: '#00A4A6',
  vpc: '#8C4FFF',
  subnet: '#7AA116',
  global: '#E9EBED',
}

function BadgeGlyph({ kind }: { kind: GroupKind | undefined }) {
  switch (kind) {
    case 'vpc':
      return (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
          <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" strokeWidth="2" strokeDasharray="4 2.5" />
          <circle cx="12" cy="12" r="2.6" fill="currentColor" />
        </svg>
      )
    case 'subnet':
      return (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
          <rect x="3" y="3" width="8" height="8" stroke="currentColor" strokeWidth="2" />
          <rect x="13" y="13" width="8" height="8" stroke="currentColor" strokeWidth="2" />
          <path d="M13 7h4v2M11 17H7v-2" stroke="currentColor" strokeWidth="1.6" />
        </svg>
      )
    case 'region':
      return (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
          <ellipse cx="12" cy="12" rx="4" ry="9" stroke="currentColor" strokeWidth="1.6" />
          <path d="M3 12h18" stroke="currentColor" strokeWidth="1.6" />
        </svg>
      )
    
    default:
      // AWS Cloud / global
      return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
          <path
            d="M7 18a4 4 0 01-.6-7.96A5.5 5.5 0 0117.2 9.2 4.4 4.4 0 0116.6 18H7z"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinejoin="round"
          />
        </svg>
      )
  }
}

function AwsGroup({ data }: NodeProps<AwsGroupNode>) {
  const kind = data.kind
  const color = data.color || GROUP_FALLBACK_COLORS[kind ?? 'vpc'] || '#8a8f98'
  // dark glyph on light badges, light glyph on saturated badges
  const glyphColor = kind === 'global' ? '#16191f' : '#ffffff'
  return (
    <div
      className="aws-group"
      // region / VPC / subnet are dotted containers; the AWS Cloud box is solid
      style={{ borderColor: color, borderStyle: 'dotted' }}
    >
      <div className="aws-group__header">
        <span className="aws-group__badge" style={{ background: color, color: glyphColor }}>
          <BadgeGlyph kind={kind} />
        </span>
        <span className="aws-group__title">{data.label}</span>
      </div>
    </div>
  )
}

const nodeTypes = { aws: AwsNode, awsGroup: AwsGroup }

const KNOWN_TYPES: AwsResourceType[] = [
  'vpc', 'ec2', 's3', 'rds', 'lambda', 'cloudwatch',
  'elb', 'ebs', 'dynamodb', 'ecr', 'apigateway', 'amplify', 'route53',
]

// Containment tells the story in AWS reference diagrams — no edges drawn.
const GROUP_Z: Record<string, number> = { region: -3, vpc: -2, subnet: -1, global: -2 }

function toFlow(data: ScanResult): { nodes: Node[]; edges: Edge[] } {
  const groupNodes: Node[] = (data.groups ?? []).map((g) => ({
    id: `group-${g.id}`,
    type: 'awsGroup',
    position: { x: g.x, y: g.y },
    data: { label: g.label, color: g.color ?? '', kind: g.kind },
    style: { width: g.width, height: g.height },
    // stacking: region under vpc under subnet, all under resource nodes
    zIndex: GROUP_Z[g.kind ?? 'vpc'] ?? -1,
    selectable: false,
    draggable: false,
  }))

  // Real AWS diagrams show the VPC as a container outline, not a node —
  // drop VPC node cards from the canvas.
  const resourceNodes: Node[] = data.nodes
    .filter((n) => n.type !== 'vpc')
    .map((n) => ({
      id: n.id,
      type: 'aws',
      position: { x: n.x, y: n.y },
      data: {
        label: n.label,
        sublabel: n.sublabel,
        resourceType: KNOWN_TYPES.includes(n.type) ? n.type : 'vpc',
      },
    }))

  return { nodes: [...groupNodes, ...resourceNodes], edges: [] }
}

interface ResourceFlowProps {
  data: ScanResult
  onRescan: () => void
}

// Stable identity per scan result so the (uncontrolled, read-only) canvas
// remounts only when a new scan produces new data.
let nextFlowId = 0
const flowIds = new WeakMap<ScanResult, number>()
function flowIdFor(data: ScanResult): number {
  let id = flowIds.get(data)
  if (id == null) {
    id = ++nextFlowId
    flowIds.set(data, id)
  }
  return id
}

export function ResourceFlow({ data, onRescan }: ResourceFlowProps) {
  const flow = useMemo(() => toFlow(data), [data])

  return (
    <div className="resource-flow">
      <button type="button" className="pill-button resource-flow__rescan" onClick={onRescan}>
        Rescan
      </button>
      <ReactFlow
        key={flowIdFor(data)}
        defaultNodes={flow.nodes}
        defaultEdges={flow.edges}
        nodeTypes={nodeTypes}
        colorMode="dark"
        fitView
        fitViewOptions={{ padding: 0.2 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        minZoom={0.3}
        maxZoom={2}
      >
        <Background variant={BackgroundVariant.Lines} gap={24} color="rgba(255,255,255,.08)" />
      </ReactFlow>
    </div>
  )
}
