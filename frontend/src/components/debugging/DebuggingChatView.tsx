import type { ChatMessage } from '../../types'
import { MessageList } from '../chat/MessageList'
import { Composer } from '../chat/Composer'

interface DebuggingChatViewProps {
  headerMeta: string
  messages: ChatMessage[]
  isThinking: boolean
  checkLogsDisabled: boolean
  onCheckLogs: () => void
  onSend: (text: string) => void
}

export function DebuggingChatView({
  headerMeta,
  messages,
  isThinking,
  checkLogsDisabled,
  onCheckLogs,
  onSend,
}: DebuggingChatViewProps) {
  return (
    <>
      <div className="view-header">
        <div>
          <div className="view-header__title">Debugging</div>
          <div className="view-header__subtitle">CloudWatch errors → code → suggested fix</div>
        </div>
        <div className="view-header__meta">{headerMeta}</div>
      </div>
      <div className="chat-scroll">
        <div className="chat-column">
          {messages.length === 0 && (
            <div className="empty-state">
              <p className="empty-state__lead">
                Pull recent errors from <code>my-container-logs</code>, match them to{' '}
                <code>hello-world/</code>, and get a suggested fix.
              </p>
              <div className="empty-state__suggestions">
                <button type="button" className="pill-button" onClick={onCheckLogs} disabled={checkLogsDisabled}>
                  Check logs
                </button>
              </div>
            </div>
          )}
          <MessageList
            appName="Debugging"
            messages={messages}
            isThinking={isThinking}
            onResolveAction={() => {}}
          />
        </div>
      </div>
      <Composer isThinking={isThinking} onSend={onSend} />
    </>
  )
}
