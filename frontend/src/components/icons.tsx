import type { AwsResourceType } from '../types'

export function LogoIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M6 8l4 4-4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <line x1="12" y1="16" x2="18" y2="16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

export function ResourceMapIcon() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none">
      <circle cx="6" cy="6" r="2.6" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="18" cy="6" r="2.6" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="12" cy="18" r="2.6" stroke="currentColor" strokeWidth="1.8" />
      <path d="M8.3 7.3L10.5 15.5M15.7 7.3L13.5 15.5M8.6 6H15.4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

export function AgentModeIcon() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none">
      <rect x="5" y="8" width="14" height="11" rx="3" stroke="currentColor" strokeWidth="1.8" />
      <path d="M12 8V5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="12" cy="4" r="1.4" fill="currentColor" />
      <circle cx="9.3" cy="13.2" r="1.3" fill="currentColor" />
      <circle cx="14.7" cy="13.2" r="1.3" fill="currentColor" />
    </svg>
  )
}

export function NewChatIcon() {
  // OpenAI-style "new chat" compose icon: a note with a pencil.
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none">
      <path
        d="M12 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-6"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function DebuggingIcon() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none">
      <ellipse cx="12" cy="13" rx="5.2" ry="6.2" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M12 6.8V4.5M9.2 5.2L8 3.8M14.8 5.2L16 3.8"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path d="M12 7.5v11.2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path
        d="M6.8 10.2H4.5M6.8 13.5H4.2M6.8 16.8H4.5M17.2 10.2H19.5M17.2 13.5H19.8M17.2 16.8H19.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function SendIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none">
      <path d="M12 19V5M5 12l7-7 7 7" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function ChevronIcon({ size = 12 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function CheckIcon({ size = 10, strokeWidth = 3 }: { size?: number; strokeWidth?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M5 13l4 4L19 7" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function VpcIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
      <rect x="3" y="3" width="18" height="18" rx="4" stroke="currentColor" strokeWidth="1.4" strokeDasharray="3 2" />
      <circle cx="12" cy="12" r="2.2" fill="currentColor" />
    </svg>
  )
}

function Ec2Icon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
      <rect x="4" y="5" width="16" height="4" rx="1" stroke="currentColor" strokeWidth="1.4" />
      <rect x="4" y="10" width="16" height="4" rx="1" stroke="currentColor" strokeWidth="1.4" />
      <rect x="4" y="15" width="16" height="4" rx="1" stroke="currentColor" strokeWidth="1.4" />
      <circle cx="7" cy="7" r="0.8" fill="currentColor" />
      <circle cx="7" cy="12" r="0.8" fill="currentColor" />
      <circle cx="7" cy="17" r="0.8" fill="currentColor" />
    </svg>
  )
}

function S3Icon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
      <path d="M5 6h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M6 6h12l-1.5 13a1 1 0 01-1 .9H8.5a1 1 0 01-1-.9L6 6z" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  )
}

function RdsIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
      <ellipse cx="12" cy="6" rx="7" ry="2.5" stroke="currentColor" strokeWidth="1.4" />
      <path d="M5 6v12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5V6" stroke="currentColor" strokeWidth="1.4" />
      <path d="M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  )
}

function LambdaIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
      <path d="M9 5l3 7-3.6 7M12 12l3.6 7" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function CloudWatchIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="1.5" />
      <path d="M12 8v4l3 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// AWS Architecture Icons category colors (per-type accent)
export const RESOURCE_COLORS: Record<AwsResourceType, string> = {
  ec2: '#ED7100', // Compute
  lambda: '#ED7100',
  ecr: '#ED7100', // Containers
  s3: '#7AA116', // Storage
  ebs: '#7AA116',
  rds: '#C925D1', // Database
  dynamodb: '#C925D1',
  vpc: '#8C4FFF', // Networking
  elb: '#8C4FFF',
  route53: '#8C4FFF',
  apigateway: '#8C4FFF',
  amplify: '#DD344C', // Front-end web & mobile
  cloudwatch: '#E7157B', // Management & governance
}

// Official AWS Architecture icon SVGs served from /aws_icons
const ICON_FILES: Record<AwsResourceType, string> = {
  vpc: '', // no VPC icon in the set — keep the hand-drawn fallback
  ec2: 'EC2.svg',
  s3: 'Simple Storage Service.svg',
  rds: 'RDS.svg',
  lambda: 'Lambda.svg',
  cloudwatch: 'CloudWatch.svg',
  elb: 'Elastic Load Balancing.svg',
  ebs: 'Elastic Block Store.svg',
  dynamodb: 'DynamoDB.svg',
  ecr: 'Elastic Container Registry.svg',
  apigateway: 'API Gateway.svg',
  amplify: 'Amplify.svg',
  route53: 'Route 53.svg',
}

function FallbackIcon({ type }: { type: AwsResourceType }) {
  switch (type) {
    case 'ec2':
      return <Ec2Icon />
    case 's3':
      return <S3Icon />
    case 'rds':
      return <RdsIcon />
    case 'lambda':
      return <LambdaIcon />
    case 'cloudwatch':
      return <CloudWatchIcon />
    default:
      return <VpcIcon />
  }
}

export function ResourceIcon({ type }: { type: AwsResourceType }) {
  const file = ICON_FILES[type]
  if (!file) return <FallbackIcon type={type} />
  return (
    <img
      className="aws-node__official-icon"
      src={`/aws_icons/${encodeURIComponent(file)}`}
      alt=""
      draggable={false}
    />
  )
}
