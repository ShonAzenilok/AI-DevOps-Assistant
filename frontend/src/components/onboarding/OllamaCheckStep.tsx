import { useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import { CheckIcon } from '../icons'

const POLL_INTERVAL_MS = 1500

interface OllamaCheckStepProps {
  appName: string
  onEnter: () => void
}

function StatusIndicator({ state }: { state: 'pending' | 'spinning' | 'done' }) {
  if (state === 'done') {
    return (
      <span className="check-dot" style={{ color: 'var(--bg)' }}>
        <CheckIcon />
      </span>
    )
  }
  if (state === 'spinning') return <span className="spinner" />
  return <span className="pending-dot" />
}

export function OllamaCheckStep({ appName, onEnter }: OllamaCheckStepProps) {
  const [instanceRunning, setInstanceRunning] = useState(false)
  const [modelReady, setModelReady] = useState(false)
  const [model, setModel] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const stopped = useRef(false)

  useEffect(() => {
    stopped.current = false
    let timer: number | undefined

    const poll = async () => {
      try {
        const status = await api.getOllamaStatus()
        if (stopped.current) return
        setInstanceRunning(status.instanceRunning)
        setModelReady(status.modelReady)
        if (status.model) setModel(status.model)
        setError(null)
        if (status.instanceRunning && status.modelReady) return // done — stop polling
      } catch (err) {
        if (stopped.current) return
        setInstanceRunning(false)
        setModelReady(false)
        setError(err instanceof Error ? err.message : 'Could not check Ollama status.')
      }
      timer = window.setTimeout(poll, POLL_INTERVAL_MS)
    }

    poll()
    return () => {
      stopped.current = true
      window.clearTimeout(timer)
    }
  }, [])

  const ready = instanceRunning && modelReady
  const modelName = model ?? 'qwen3.5:4b'

  return (
    <div className="ollama-step fade-up">
      <h2>Connecting to Ollama</h2>
      <p>Looking for a local Ollama instance and verifying the {modelName} model.</p>

      <div className="ollama-checklist">
        <div className="ollama-checklist__row">
          <StatusIndicator state={instanceRunning ? 'done' : 'spinning'} />
          <span className="ollama-checklist__label">Ollama instance detected on localhost:11434</span>
        </div>
        <div className="ollama-checklist__row">
          <StatusIndicator state={modelReady ? 'done' : instanceRunning ? 'spinning' : 'pending'} />
          <span className={`ollama-checklist__label${modelReady ? '' : ' ollama-checklist__label--pending'}`}>
            Model {modelName} ready
          </span>
        </div>
      </div>

      {error && <p className="onboarding-error">{error}</p>}

      <button
        type="button"
        className="pill-button pill-button--wide"
        disabled={!ready}
        onClick={onEnter}
      >
        Enter {appName}
      </button>
    </div>
  )
}
