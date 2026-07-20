import { useState } from 'react'
import type { AwsConfig } from '../../types'
import { api } from '../../api/client'

const REGIONS = [
  { value: 'us-east-1', label: 'us-east-1 — N. Virginia' },
  { value: 'us-west-2', label: 'us-west-2 — Oregon' },
  { value: 'eu-west-1', label: 'eu-west-1 — Ireland' },
  { value: 'ap-southeast-1', label: 'ap-southeast-1 — Singapore' },
]

interface AwsConnectStepProps {
  config: AwsConfig
  onChange: (config: AwsConfig) => void
  onVerified: (accountId: string) => void
}

export function AwsConnectStep({ config, onChange, onVerified }: AwsConnectStepProps) {
  const [verifying, setVerifying] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const filled = config.accessKeyId.trim().length > 0 && config.secretAccessKey.trim().length > 0

  const verify = async () => {
    if (!filled || verifying) return
    setVerifying(true)
    setError(null)
    try {
      const res = await api.verifyAws(config)
      onVerified(res.accountId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Verification failed.')
      setVerifying(false)
    }
  }

  return (
    <div className="onboarding-form fade-up">
      <div className="onboarding-form__heading">
        <h2>Connect your AWS account</h2>
        <p>Credentials stay local — used only to call the AWS APIs you approve.</p>
      </div>
      <div className="field-card">
        <div className="field">
          <label htmlFor="aws-access-key">Access key ID</label>
          <input
            id="aws-access-key"
            value={config.accessKeyId}
            onChange={(e) => onChange({ ...config, accessKeyId: e.target.value })}
            placeholder="AKIA..."
            autoComplete="off"
            spellCheck={false}
            disabled={verifying}
          />
        </div>
        <div className="field">
          <label htmlFor="aws-secret-key">Secret access key</label>
          <input
            id="aws-secret-key"
            type="password"
            value={config.secretAccessKey}
            onChange={(e) => onChange({ ...config, secretAccessKey: e.target.value })}
            placeholder="••••••••••••••••"
            autoComplete="off"
            disabled={verifying}
          />
        </div>
        <div className="field">
          <label htmlFor="aws-region">Region</label>
          <select
            id="aws-region"
            value={config.region}
            onChange={(e) => onChange({ ...config, region: e.target.value })}
            disabled={verifying}
          >
            {REGIONS.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </div>
      </div>
      {error && <p className="onboarding-error">{error}</p>}
      <button
        type="button"
        className="pill-button pill-button--wide"
        disabled={!filled || verifying}
        onClick={verify}
      >
        {verifying ? 'Verifying…' : 'Continue'}
      </button>
    </div>
  )
}
