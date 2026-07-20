import type { MainView } from '../types'
import { AgentModeIcon, LogoIcon, NewChatIcon, ResourceMapIcon } from './icons'

interface SidebarProps {
  view: MainView
  onSelect: (view: MainView) => void
  onNewChat: () => void
}

export function Sidebar({ view, onSelect, onNewChat }: SidebarProps) {
  return (
    <div className="rail">
      <div className="logo-tile">
        <LogoIcon />
      </div>
      <button type="button" title="New chat" className="rail-button" onClick={onNewChat}>
        <NewChatIcon />
      </button>
      <button
        type="button"
        title="Resource map"
        className={`rail-button${view === 'resourceMap' ? ' active' : ''}`}
        onClick={() => onSelect('resourceMap')}
      >
        <ResourceMapIcon />
      </button>
      <button
        type="button"
        title="Agent mode"
        className={`rail-button${view === 'agent' ? ' active' : ''}`}
        onClick={() => onSelect('agent')}
      >
        <AgentModeIcon />
      </button>
    </div>
  )
}
