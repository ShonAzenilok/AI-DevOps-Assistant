const SUGGESTIONS = [
  'Show my running EC2 instances',
  'Show my Lambda functions',
  'List my S3 buckets',
  'Any errors in the last hour?',
]

interface EmptyStateProps {
  onPick: (text: string) => void
}

export function EmptyState({ onPick }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <h1>What's going on in your infra?</h1>
      <div className="empty-state__suggestions">
        {SUGGESTIONS.map((s) => (
          <button key={s} type="button" className="ghost-pill" onClick={() => onPick(s)}>
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}
