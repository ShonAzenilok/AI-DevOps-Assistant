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
        A local-first AI DevOps assistant.
        DevBot gives you complete control over your cloud environment by combining CRUD capabilities via Boto3
        with local Terraform execution.
        Powered entirely on your machine using Ollama and the qwen3.5:4b model.
      </p>
      <button type="button" className="pill-button" onClick={onNext}>
        Get started
      </button>
    </div>
  )
}
