import { useCallback, useRef, useState } from 'react'
import type { AppPhase, AwsConfig, ChatMessage, MainView, PendingAction, ScanState } from './types'
import { api, ApiError } from './api/client'
import { Sidebar } from './components/Sidebar'
import { OnboardingLayout } from './components/onboarding/OnboardingLayout'
import { WelcomeStep } from './components/onboarding/WelcomeStep'
import { AwsConnectStep } from './components/onboarding/AwsConnectStep'
import { ChatView } from './components/chat/ChatView'
import { ResourceMapView } from './components/resourceMap/ResourceMapView'

const APP_NAME = 'DevBot'

function errorText(err: unknown): string {
  if (err instanceof ApiError && err.backendUnavailable) {
    return 'Backend unavailable — start the FastAPI server on localhost:8000 and try again.'
  }
  return err instanceof Error ? err.message : 'Something went wrong.'
}

export default function App() {
  const [phase, setPhase] = useState<AppPhase>('welcome')
  const [awsConfig, setAwsConfig] = useState<AwsConfig>({
    accessKeyId: '',
    secretAccessKey: '',
    region: 'us-east-1',
  })
  const [accountId, setAccountId] = useState<string | null>(null)
  const [view, setView] = useState<MainView>('agent')

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isThinking, setIsThinking] = useState(false)
  const [scan, setScan] = useState<ScanState>({ status: 'idle' })
  // Bumped on "new chat" — used to remount the chat (clearing the composer's
  // local input) and to discard any reply from a request started earlier.
  const [chatSession, setChatSession] = useState(0)
  const chatSessionRef = useRef(0)

  const sendMessage = useCallback(
    async (raw: string) => {
      const text = raw.trim()
      if (!text || isThinking) return
      const session = chatSessionRef.current
      const history = messages
        .filter((m) => !m.isError)
        .map((m) => ({ role: m.role, text: m.text }))
      setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'user', text }])
      setIsThinking(true)

      // The assistant message is created by the first streamed event and grown
      // in place as more arrive, so the answer appears as the model writes it.
      const assistantId = crypto.randomUUID()
      const upsertAssistant = (update: (m: ChatMessage) => ChatMessage) => {
        if (chatSessionRef.current !== session) return
        setIsThinking(false)
        setMessages((prev) => {
          const i = prev.findIndex((m) => m.id === assistantId)
          if (i === -1) {
            return [...prev, update({ id: assistantId, role: 'assistant', text: '', tools: [] })]
          }
          const next = [...prev]
          next[i] = update(next[i])
          return next
        })
      }

      let gotContent = false
      try {
        await api.sendChatStream(text, history, {
          onToken: (chunk) => {
            gotContent = true
            upsertAssistant((m) => ({ ...m, text: m.text + chunk }))
          },
          onTool: (tool) => {
            gotContent = true
            upsertAssistant((m) => ({ ...m, tools: [...(m.tools ?? []), tool] }))
          },
          onConfirm: (action) => {
            gotContent = true
            upsertAssistant((m) => ({ ...m, actions: [...(m.actions ?? []), action] }))
          },
        })
        if (!gotContent) {
          upsertAssistant((m) => ({
            ...m,
            text: "I didn't get anything back for that — try rephrasing.",
          }))
        }
      } catch (err) {
        if (chatSessionRef.current !== session) return
        setMessages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), role: 'assistant', text: errorText(err), isError: true },
        ])
      } finally {
        if (chatSessionRef.current === session) setIsThinking(false)
      }
    },
    [isThinking, messages],
  )

  // Confirm or cancel a staged destructive action: call the backend, then
  // reflect the outcome (executed/failed/cancelled + result) on the card.
  const resolveAction = useCallback(
    async (messageId: string, actionId: string, verb: 'confirm' | 'cancel') => {
      const session = chatSessionRef.current
      const patch = (update: (a: PendingAction) => PendingAction) => {
        if (chatSessionRef.current !== session) return
        setMessages((prev) =>
          prev.map((m) =>
            m.id === messageId
              ? { ...m, actions: (m.actions ?? []).map((a) => (a.id === actionId ? update(a) : a)) }
              : m,
          ),
        )
      }
      try {
        const result =
          verb === 'confirm'
            ? await api.confirmAction(actionId)
            : await api.cancelAction(actionId)
        patch((a) => ({
          ...a,
          status: result.status,
          resultSummary: result.summary ?? undefined,
          resultOutput: result.output ?? undefined,
        }))
      } catch (err) {
        patch((a) => ({ ...a, status: 'failed', resultSummary: errorText(err) }))
      }
    },
    [],
  )

  const startNewChat = useCallback(() => {
    chatSessionRef.current += 1
    setChatSession(chatSessionRef.current)
    setMessages([])
    setIsThinking(false)
    setScan({ status: 'idle' })
    setView('agent')
  }, [])

  const startScan = useCallback(async () => {
    setScan((prev) => (prev.status === 'scanning' ? prev : { status: 'scanning' }))
    try {
      const data = await api.scanResources()
      if (data.accountId) setAccountId(data.accountId)
      setScan({ status: 'ready', data })
    } catch (err) {
      setScan({ status: 'error', error: errorText(err) })
    }
  }, [])

  const headerMeta = `${accountId ?? 'Not connected'} · ${awsConfig.region}`

  if (phase !== 'chat') {
    return (
      <div className="app">
        <OnboardingLayout step={phase}>
          {phase === 'welcome' && <WelcomeStep appName={APP_NAME} onNext={() => setPhase('aws')} />}
          {phase === 'aws' && (
            <AwsConnectStep
              config={awsConfig}
              onChange={setAwsConfig}
              onVerified={(verifiedAccountId) => {
                setAccountId(verifiedAccountId)
                setPhase('chat')
              }}
            />
          )}
        </OnboardingLayout>
      </div>
    )
  }

  return (
    <div className="app">
      <Sidebar view={view} onSelect={setView} onNewChat={startNewChat} />
      <div className="main-column">
        {view === 'agent' ? (
          <ChatView
            key={chatSession}
            appName={APP_NAME}
            headerMeta={headerMeta}
            messages={messages}
            isThinking={isThinking}
            onSend={sendMessage}
            onResolveAction={resolveAction}
          />
        ) : (
          <ResourceMapView headerMeta={headerMeta} scan={scan} onStartScan={startScan} />
        )}
      </div>
    </div>
  )
}
