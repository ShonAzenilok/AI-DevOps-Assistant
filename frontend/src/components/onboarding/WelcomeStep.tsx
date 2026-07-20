import { LogoIcon } from '../icons'

interface WelcomeStepProps {
  appName: string
  onNext: () => void
}

export function WelcomeStep({ appName, onNext }: WelcomeStepProps) {
  return (
    <div className="welcome-step fade-up">
      <div className="logo-tile">
        <LogoIcon size={28} />
      </div>
      <h1>Meet {appName}</h1>
      <p>
        A local-first AI DevOps assistant for AWS.
        Connect your account, then chat with Claude on Amazon Bedrock to explore
        resources and run AWS CLI actions through the managed AWS MCP Server —
        with confirmation before anything write or destructive runs.
      </p>
      <button type="button" className="pill-button" onClick={onNext}>
        Get started
      </button>
    </div>
  )
}
