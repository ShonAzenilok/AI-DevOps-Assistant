export type OnboardingStep = 'welcome' | 'aws'
export type AppPhase = OnboardingStep | 'chat'
export type MainView = 'agent' | 'resourceMap'

export interface AwsConfig {
  accessKeyId: string
  secretAccessKey: string
  region: string
}

export interface ToolCall {
  label: string
  detail: string
  durationMs?: number
  output?: string
}

export type ActionStatus = 'pending' | 'executed' | 'cancelled' | 'failed'

/** A staged write/destructive action awaiting the user's Confirm/Cancel. */
export interface PendingAction {
  id: string
  label: string
  detail: string
  resource: Record<string, string>
  status: ActionStatus
  resultSummary?: string
  resultOutput?: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  tools?: ToolCall[]
  actions?: PendingAction[]
  isError?: boolean
}

export type AwsResourceType =
  | 'vpc'
  | 'ec2'
  | 's3'
  | 'rds'
  | 'lambda'
  | 'cloudwatch'
  | 'elb'
  | 'ebs'
  | 'dynamodb'
  | 'ecr'
  | 'apigateway'
  | 'amplify'
  | 'route53'

export type GroupKind = 'region' | 'vpc' | 'subnet' | 'global'

export interface ScanNode {
  id: string
  label: string
  sublabel: string
  type: AwsResourceType
  x: number
  y: number
  /** Containing group id; x/y are relative to that parent. */
  parentId?: string | null
}

export interface ScanEdge {
  id?: string
  source: string
  target: string
}

export interface ScanGroup {
  id: string
  label: string
  x: number
  y: number
  width: number
  height: number
  color?: string
  kind?: GroupKind
  /** Parent group id for nesting (vpc under region, subnet under vpc). */
  parentId?: string | null
}

export interface ScanResult {
  accountId?: string
  region?: string
  nodes: ScanNode[]
  edges: ScanEdge[]
  groups?: ScanGroup[]
}

export type ScanState =
  | { status: 'idle' }
  | { status: 'scanning' }
  | { status: 'ready'; data: ScanResult }
  | { status: 'error'; error: string }
