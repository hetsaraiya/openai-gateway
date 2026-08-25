import { Bot, Eraser, LoaderCircle, LockKeyhole, Send, Sparkles, Square, User } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"

import {
  ApiError,
  createChatCompletion,
  providerFor,
  providerLabel,
  type ChatMessage,
  type Dashboard,
} from "../lib/api"
import { Button } from "../components/ui/button"
import { Callout } from "../components/ui/callout"
import { cn } from "../lib/utils"

type Message = ChatMessage & { id: string }

export function Chat({ data, gatewayKey }: { data: Dashboard | null; gatewayKey: string }) {
  const models = useMemo(
    () => (data?.models ?? []).filter((model) => model.supported_endpoints?.includes("/v1/chat/completions")),
    [data?.models],
  )
  const groups = useMemo(() => {
    const result = new Map<string, typeof models>()
    for (const model of models) {
      const provider = providerFor(model)
      result.set(provider, [...(result.get(provider) ?? []), model])
    }
    return [...result.entries()]
  }, [models])
  const [model, setModel] = useState("")
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState("")
  const [error, setError] = useState("")
  const [sending, setSending] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const endRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!models.length) {
      setModel("")
      return
    }
    setModel((current) => models.some((item) => item.id === current) ? current : models[0].id)
  }, [models])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" })
  }, [messages, sending])

  useEffect(() => () => abortRef.current?.abort(), [])

  async function submit() {
    const content = draft.trim()
    if (!content || !model || sending) return
    const userMessage: Message = { id: crypto.randomUUID(), role: "user", content }
    const nextMessages = [...messages, userMessage]
    setMessages(nextMessages)
    setDraft("")
    setError("")
    setSending(true)
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const reply = await createChatCompletion(
        model,
        nextMessages.map(({ role, content: text }) => ({ role, content: text })),
        gatewayKey,
        controller.signal,
      )
      setMessages((current) => [
        ...current,
        { id: crypto.randomUUID(), role: "assistant", content: reply },
      ])
    } catch (cause) {
      if ((cause as Error).name !== "AbortError") {
        setError((cause as ApiError).message || "The request failed.")
      }
    } finally {
      abortRef.current = null
      setSending(false)
    }
  }

  function clearChat() {
    abortRef.current?.abort()
    setMessages([])
    setError("")
    setSending(false)
  }

  return (
    <section className="overflow-hidden rounded-2xl border border-line bg-surface shadow-panel">
      <header className="flex flex-col gap-4 border-b border-line px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="grid size-8 place-items-center rounded-lg bg-accent-soft text-accent-text">
              <Sparkles size={16} aria-hidden="true" />
            </span>
            <div>
              <h1 className="text-[15px] font-semibold text-ink">Chat playground</h1>
              <p className="mt-0.5 flex items-center gap-1.5 text-[11px] text-subtle">
                <LockKeyhole size={11} aria-hidden="true" />
                This conversation stays in this tab and is not saved.
              </p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <label className="sr-only" htmlFor="chat-model">Model</label>
          <select
            id="chat-model"
            value={model}
            onChange={(event) => setModel(event.target.value)}
            disabled={!models.length || sending}
            className="h-9 min-w-0 flex-1 rounded-lg border border-line bg-elevated px-3 text-xs text-ink outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/20 sm:w-72"
          >
            {!models.length ? <option value="">No chat models available</option> : null}
            {groups.map(([provider, providerModels]) => (
              <optgroup key={provider} label={providerLabel(provider)}>
                {providerModels.map((item) => (
                  <option key={item.id} value={item.id}>{item.display_name || item.id}</option>
                ))}
              </optgroup>
            ))}
          </select>
          <Button variant="ghost" size="icon-sm" onClick={clearChat} disabled={!messages.length && !sending} aria-label="Clear chat">
            <Eraser size={15} aria-hidden="true" />
          </Button>
        </div>
      </header>

      <div className="flex min-h-[calc(100dvh-15rem)] flex-col">
        <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-6" aria-live="polite">
          {!messages.length ? (
            <div className="mx-auto flex max-w-md flex-col items-center justify-center py-16 text-center">
              <span className="grid size-12 place-items-center rounded-2xl border border-line bg-elevated text-accent-text shadow-panel">
                <Bot size={21} aria-hidden="true" />
              </span>
              <h2 className="mt-4 text-sm font-semibold text-ink">Choose any model and start chatting</h2>
              <p className="mt-1.5 text-xs leading-5 text-muted">
                Models are grouped by provider. Switching models keeps the visible conversation in this tab only.
              </p>
            </div>
          ) : (
            <div className="mx-auto max-w-3xl space-y-5">
              {messages.map((message) => (
                <article key={message.id} className={cn("flex gap-3", message.role === "user" && "justify-end")}>
                  {message.role === "assistant" ? (
                    <span className="grid size-8 shrink-0 place-items-center rounded-lg border border-line bg-elevated text-accent-text">
                      <Bot size={15} aria-hidden="true" />
                    </span>
                  ) : null}
                  <div className={cn(
                    "max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-[13px] leading-6",
                    message.role === "user" ? "bg-accent text-accent-fg" : "border border-line bg-elevated text-ink",
                  )}>
                    {message.content}
                  </div>
                  {message.role === "user" ? (
                    <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-accent text-accent-fg">
                      <User size={15} aria-hidden="true" />
                    </span>
                  ) : null}
                </article>
              ))}
              {sending ? (
                <div className="flex items-center gap-3 text-xs text-muted">
                  <span className="grid size-8 place-items-center rounded-lg border border-line bg-elevated text-accent-text">
                    <LoaderCircle size={15} className="animate-spin" aria-hidden="true" />
                  </span>
                  Thinking with {model}…
                </div>
              ) : null}
              <div ref={endRef} />
            </div>
          )}
        </div>

        <div className="border-t border-line bg-elevated/70 p-4 sm:p-5">
          <div className="mx-auto max-w-3xl">
            {error ? <Callout tone="danger" title="Message not sent">{error}</Callout> : null}
            <div className={cn("flex items-end gap-2 rounded-2xl border border-line bg-surface p-2 shadow-panel", error && "mt-3")}>
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault()
                    void submit()
                  }
                }}
                placeholder={model ? `Message ${model}` : "Connect a provider to start chatting"}
                disabled={!model || sending}
                rows={1}
                className="max-h-40 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-[13px] leading-5 text-ink outline-none placeholder:text-subtle disabled:cursor-not-allowed"
                aria-label="Chat message"
              />
              {sending ? (
                <Button size="icon" variant="secondary" onClick={() => abortRef.current?.abort()} aria-label="Stop response">
                  <Square size={13} fill="currentColor" aria-hidden="true" />
                </Button>
              ) : (
                <Button size="icon" onClick={() => void submit()} disabled={!draft.trim() || !model} aria-label="Send message">
                  <Send size={15} aria-hidden="true" />
                </Button>
              )}
            </div>
            <p className="mt-2 text-center text-[10px] text-subtle">Enter to send · Shift + Enter for a new line</p>
          </div>
        </div>
      </div>
    </section>
  )
}
