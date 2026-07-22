import type {
  ActionResultResponse,
  AwsConfig,
  AwsVerifyResponse,
  ChatHistoryItem,
  PendingAction,
  ScanResult,
  ToolCall,
} from '../types'

const API_BASE = '/api'

export type { ActionResultResponse, AwsVerifyResponse, ChatHistoryItem }

export class ApiError extends Error {
  readonly status: number | null
  readonly backendUnavailable: boolean

  constructor(message: string, status: number | null = null, backendUnavailable = false) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.backendUnavailable = backendUnavailable
  }
}

async function fetchOrThrow(path: string, init?: RequestInit): Promise<Response> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    })
  } catch {
    throw new ApiError('Backend unavailable', null, true)
  }
  if (!res.ok) {
    // 500 is what the Vite dev proxy returns when FastAPI isn't running;
    // 502-504 are the equivalent from a real reverse proxy.
    const unavailable = [500, 502, 503, 504].includes(res.status)
    let detail = `Request failed (${res.status})`
    try {
      const body: unknown = await res.json()
      if (body && typeof body === 'object' && 'detail' in body) {
        detail = String((body as { detail: unknown }).detail)
      }
    } catch {
      // non-JSON error body — keep the generic message
    }
    throw new ApiError(detail, res.status, unavailable)
  }
  return res
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetchOrThrow(path, init)
  return res.json() as Promise<T>
}

export interface ChatStreamHandlers {
  onToken: (text: string) => void
  onTool: (tool: ToolCall) => void
  /** A destructive action was staged and needs the user's Confirm/Cancel. */
  onConfirm?: (action: PendingAction) => void
}

type ChatStreamEvent =
  | { type: 'token'; text: string }
  | { type: 'tool'; tool: ToolCall }
  | { type: 'confirm'; action: PendingAction }
  | { type: 'error'; detail: string }
  | { type: 'done' }

async function readNdjsonStream(res: Response, handlers: ChatStreamHandlers): Promise<void> {
  if (!res.body) throw new ApiError('Streaming is not supported by this browser')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const handleLine = (line: string) => {
    if (!line.trim()) return
    let event: ChatStreamEvent
    try {
      event = JSON.parse(line) as ChatStreamEvent
    } catch {
      return
    }
    if (event.type === 'token') handlers.onToken(event.text)
    else if (event.type === 'tool') handlers.onTool(event.tool)
    else if (event.type === 'confirm') handlers.onConfirm?.(event.action)
    else if (event.type === 'error') throw new ApiError(event.detail)
  }

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) handleLine(line)
  }
  handleLine(buffer)
}

export const api = {
  /** Streams one agent turn, invoking handlers as tokens and tool calls arrive.
   *  Resolves when the turn completes; rejects with ApiError on failure. */
  async sendChatStream(
    message: string,
    history: ChatHistoryItem[],
    handlers: ChatStreamHandlers,
  ): Promise<void> {
    const res = await fetchOrThrow('/chat', {
      method: 'POST',
      body: JSON.stringify({ message, history }),
    })
    await readNdjsonStream(res, handlers)
  },

  async checkLogsStream(handlers: ChatStreamHandlers): Promise<void> {
    const res = await fetchOrThrow('/debug/check-logs', { method: 'POST', body: '{}' })
    await readNdjsonStream(res, handlers)
  },

  async sendDebugChatStream(
    message: string,
    history: ChatHistoryItem[],
    handlers: ChatStreamHandlers,
  ): Promise<void> {
    const res = await fetchOrThrow('/debug/chat', {
      method: 'POST',
      body: JSON.stringify({ message, history }),
    })
    await readNdjsonStream(res, handlers)
  },

  verifyAws(config: AwsConfig): Promise<AwsVerifyResponse> {
    return request('/aws/verify', { method: 'POST', body: JSON.stringify(config) })
  },
  scanResources(): Promise<ScanResult> {
    return request('/resources/scan', { method: 'POST' })
  },
  confirmAction(actionId: string): Promise<ActionResultResponse> {
    return request(`/actions/${actionId}/confirm`, { method: 'POST' })
  },
  cancelAction(actionId: string): Promise<ActionResultResponse> {
    return request(`/actions/${actionId}/cancel`, { method: 'POST' })
  },
}
