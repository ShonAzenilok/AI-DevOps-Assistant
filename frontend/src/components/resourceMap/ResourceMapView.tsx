import type { ScanState } from '../../types'
import { ResourceFlow } from './ResourceFlow'

interface ResourceMapViewProps {
  headerMeta: string
  scan: ScanState
  onStartScan: () => void
}

export function ResourceMapView({ headerMeta, scan, onStartScan }: ResourceMapViewProps) {
  return (
    <>
      <div className="view-header">
        <div>
          <div className="view-header__title">Resource map</div>
          <div className="view-header__subtitle">Live topology of your connected AWS account</div>
        </div>
        <div className="view-header__meta">{headerMeta}</div>
      </div>
      <div className="resource-body">
        {scan.status === 'idle' && (
          <div className="resource-status fade-up">
            <p>
              Scan your connected AWS account to discover resources and draw a live topology of how
              they relate.
            </p>
            <button type="button" className="pill-button" onClick={onStartScan}>
              Start resource scan
            </button>
          </div>
        )}
        {scan.status === 'scanning' && (
          <div className="resource-status fade-up">
            <span className="spinner" />
            <p>Scanning your AWS account…</p>
          </div>
        )}
        {scan.status === 'error' && (
          <div className="resource-status fade-up">
            <p className="resource-status__error">{scan.error}</p>
            <button type="button" className="pill-button" onClick={onStartScan}>
              Retry scan
            </button>
          </div>
        )}
        {scan.status === 'ready' && <ResourceFlow data={scan.data} onRescan={onStartScan} />}
      </div>
    </>
  )
}
