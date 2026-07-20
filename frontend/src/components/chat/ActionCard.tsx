import { useState } from 'react'
import type { PendingAction } from '../../types'
import { CheckIcon, ChevronIcon } from '../icons'

interface ActionCardProps {
  action: PendingAction
  onResolve: (actionId: string, verb: 'confirm' | 'cancel') => void
}

/** Confirmation card for a staged write/destructive action. Nothing runs
 * until the user presses Confirm here. */
export function ActionCard({ action, onResolve }: ActionCardProps) {
  const [busy, setBusy] = useState(false)
  const [showOutput, setShowOutput] = useState(false)

  const resolve = (verb: 'confirm' | 'cancel') => {
    if (busy) return
    setBusy(true)
    onResolve(action.id, verb)
  }

  const resourceEntries = Object.entries(action.resource)
  const orderedEntries = [
    ...resourceEntries.filter(([key]) => key === 'Summary'),
    ...resourceEntries.filter(([key]) => key !== 'Summary'),
  ]

  if (action.status === 'pending') {
    return (
      <div className="action-card action-card--pending">
        <div className="action-card__header">Confirm action</div>
        {action.label && (
          <div className="action-card__rows">
            <div className="action-card__row">
              <span className="action-card__key">Action</span>
              <span className="action-card__value">{action.label}</span>
            </div>
          </div>
        )}
        <div className="action-card__rows">
          {orderedEntries.map(([key, value]) => (
            <div key={key} className="action-card__row">
              <span className="action-card__key">{key}</span>
              <span
                className={`action-card__value${key === 'Warning' ? ' action-card__value--warning' : ''}`}
              >
                {value}
              </span>
            </div>
          ))}
        </div>
        <div className="action-card__buttons">
          <button
            type="button"
            className="action-card__confirm"
            disabled={busy}
            onClick={() => resolve('confirm')}
          >
            Confirm
          </button>
          <button
            type="button"
            className="pill-button action-card__cancel"
            disabled={busy}
            onClick={() => resolve('cancel')}
          >
            Cancel
          </button>
        </div>
      </div>
    )
  }

  if (action.status === 'cancelled') {
    return (
      <div className="action-card action-card--done">
        <div className="action-card__result action-card__result--muted">
          Cancelled — {action.label || action.detail}
        </div>
      </div>
    )
  }

  const failed = action.status === 'failed'
  const hasOutput = Boolean(action.resultOutput)
  return (
    <div className="action-card action-card--done">
      <button
        type="button"
        className="action-card__result-row"
        onClick={() => hasOutput && setShowOutput((v) => !v)}
        disabled={!hasOutput}
      >
        {failed ? (
          <span className="action-card__result action-card__result--error">
            Failed — {action.resultSummary ?? 'unknown error'}
          </span>
        ) : (
          <>
            <span className="action-card__check">
              <CheckIcon size={8} strokeWidth={3.5} />
            </span>
            <span className="action-card__result">
              {action.resultSummary ?? `Completed — ${action.label || action.detail}`}
            </span>
          </>
        )}
        {hasOutput && (
          <span className={`tool-card__chevron${showOutput ? ' tool-card__chevron--open' : ''}`}>
            <ChevronIcon size={12} />
          </span>
        )}
      </button>
      {showOutput && <pre className="tool-card__output">{action.resultOutput}</pre>}
    </div>
  )
}
