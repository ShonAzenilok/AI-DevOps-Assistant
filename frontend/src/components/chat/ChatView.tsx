import type { ChatMessage } from '../../types'
import { EmptyState } from './EmptyState'
import { MessageList } from './MessageList'
import { Composer } from './Composer'

interface ChatViewProps {
  appName: string
  headerMeta: string
  messages: ChatMessage[]
  isThinking: boolean
  onSend: (text: string) => void
  onResolveAction: (messageId: string, actionId: string, verb: 'confirm' | 'cancel') => void
}

export function ChatView({ appName, headerMeta, messages, isThinking, onSend, onResolveAction }: ChatViewProps) {
  return (
    <>
      <div className="view-header">
        <div>
          <div className="view-header__title">{appName}</div>
          <div className="view-header__subtitle">Personal DevOps AI agent assistant</div>
        </div>
        <div className="view-header__meta">{headerMeta}</div>
      </div>
      <div className="chat-scroll">
        <div className="chat-column">
          {messages.length === 0 && <EmptyState onPick={onSend} />}
          <MessageList
            appName={appName}
            messages={messages}
            isThinking={isThinking}
            onResolveAction={onResolveAction}
          />
        </div>
      </div>
      <Composer isThinking={isThinking} onSend={onSend} />
    </>
  )
}
