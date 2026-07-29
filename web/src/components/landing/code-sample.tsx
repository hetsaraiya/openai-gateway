import { Check, Copy } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"

import { cn } from "../../lib/utils"

type Language = "curl" | "python" | "typescript"

const LANGUAGES: Language[] = ["curl", "python", "typescript"]

const SAMPLES: Record<Language, string> = {
  curl: `# Point any OpenAI client at your own gateway
curl http://localhost:8000/v1/chat/completions \\
  -H "Authorization: Bearer $GATEWAY_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "gpt-5.1-codex",
    "stream": true,
    "messages": [
      { "role": "user", "content": "Refactor this module." }
    ]
  }'`,
  python: `import os
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key=os.environ["GATEWAY_API_KEY"],
)

stream = client.chat.completions.create(
    model="gpt-5.1-codex",
    messages=[{"role": "user", "content": "Refactor this module."}],
    stream=True,
)

for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")`,
  typescript: `import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://localhost:8000/v1",
  apiKey: process.env.GATEWAY_API_KEY,
});

const stream = await client.chat.completions.create({
  model: "xai/grok-4.5",
  messages: [{ role: "user", content: "Refactor this module." }],
  stream: true,
});

for await (const part of stream) {
  process.stdout.write(part.choices[0]?.delta?.content ?? "");
}`,
}

const TOKEN_COLORS = {
  plain: "var(--ink)",
  comment: "var(--subtle)",
  string: "var(--muted)",
  keyword: "var(--accent-text)",
  call: "var(--ink)",
  number: "var(--ink)",
}

// One pass over the line: comments, then strings, then keywords, call sites and
// numbers. Deliberately shallow — it only has to look right on three snippets.
const TOKENS =
  /(#[^\n]*|\/\/[^\n]*)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|\b(const|let|await|async|import|from|def|print|return|new|True|False|None|true|false|for|in|of)\b|([A-Za-z_$][\w$]*(?=\())|\b(\d+(?:\.\d+)?)\b/g

type Token = { text: string; color: string }

function tokenize(text: string): Token[] {
  const out: Token[] = []
  let last = 0
  let match: RegExpExecArray | null
  TOKENS.lastIndex = 0
  while ((match = TOKENS.exec(text)) !== null) {
    if (match.index > last) out.push({ text: text.slice(last, match.index), color: TOKEN_COLORS.plain })
    const color = match[1]
      ? TOKEN_COLORS.comment
      : match[2]
        ? TOKEN_COLORS.string
        : match[3]
          ? TOKEN_COLORS.keyword
          : match[4]
            ? TOKEN_COLORS.call
            : TOKEN_COLORS.number
    out.push({ text: match[0], color })
    last = match.index + match[0].length
  }
  if (last < text.length) out.push({ text: text.slice(last), color: TOKEN_COLORS.plain })
  return out
}

const CHARS_PER_FRAME = 5
const FRAME_MS = 22

/** Types the active sample out character by character, once per tab selection. */
function useTypedSample(source: string) {
  const [revealed, setRevealed] = useState(0)
  const reduced = useRef(false)

  useEffect(() => {
    reduced.current = window.matchMedia("(prefers-reduced-motion: reduce)").matches
  }, [])

  useEffect(() => {
    if (reduced.current) {
      setRevealed(source.length)
      return
    }
    setRevealed(0)
    const timer = window.setInterval(() => {
      setRevealed((count) => {
        if (count >= source.length) {
          window.clearInterval(timer)
          return count
        }
        return count + CHARS_PER_FRAME
      })
    }, FRAME_MS)
    return () => window.clearInterval(timer)
  }, [source])

  return Math.min(revealed, source.length)
}

const RESPONSE_HEADERS: [string, string, boolean][] = [
  ["x-gateway-account", "codex-main", false],
  ["x-request-id", "6f2a…c41b", false],
  ["x-gateway-dedup", "hit", true],
  ["content-type", "text/event-stream", false],
]

export function CodeSample() {
  const [language, setLanguage] = useState<Language>("curl")
  const [copied, setCopied] = useState(false)
  const source = SAMPLES[language]
  const revealed = useTypedSample(source)

  const lines = useMemo(() => {
    const visible = source.slice(0, revealed).split("\n")
    const typing = revealed < source.length
    return visible.map((text, index) => ({
      tokens: tokenize(text),
      caret: typing && index === visible.length - 1,
    }))
  }, [source, revealed])

  useEffect(() => {
    if (!copied) return
    const timer = window.setTimeout(() => setCopied(false), 1600)
    return () => window.clearTimeout(timer)
  }, [copied])

  async function copy() {
    try {
      await navigator.clipboard.writeText(source)
      setCopied(true)
    } catch {
      // Clipboard access can be denied; the sample is selectable either way.
    }
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-surface shadow-panel">
      <div className="flex flex-wrap items-center gap-1 border-b border-line bg-elevated px-3 py-2.5">
        <span className="mr-3 pl-1 font-mono text-[11px] text-muted">POST /v1/chat/completions</span>
        {LANGUAGES.map((id) => (
          <button
            key={id}
            type="button"
            onClick={() => setLanguage(id)}
            aria-pressed={language === id}
            className={cn(
              "rounded-md border px-2.5 py-1.5 font-mono text-[11.5px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
              language === id
                ? "border-line bg-surface text-ink"
                : "border-transparent text-subtle hover:border-line hover:text-ink",
            )}
          >
            {id}
          </button>
        ))}
        <button
          type="button"
          onClick={() => void copy()}
          className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-line bg-surface px-2.5 py-1.5 font-mono text-[11px] text-muted transition-colors hover:border-accent hover:text-accent-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          {copied ? <Check size={12} aria-hidden="true" /> : <Copy size={12} aria-hidden="true" />}
          {copied ? "copied" : "copy"}
        </button>
      </div>

      <div className="grid lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-h-[26rem] overflow-x-auto px-6 py-6">
          <pre className="m-0 font-mono text-[13px] leading-[1.85]">
            {lines.map((line, index) => (
              <div key={index} className="min-h-[24px] whitespace-pre">
                {line.tokens.map((token, tokenIndex) => (
                  <span key={tokenIndex} style={{ color: token.color }}>
                    {token.text}
                  </span>
                ))}
                {line.caret && (
                  <span className="inline-block h-[15px] w-[7px] animate-caret bg-accent align-[-2px]" aria-hidden="true" />
                )}
              </div>
            ))}
          </pre>
        </div>

        <div className="border-line bg-elevated px-5 py-6 lg:border-l">
          <p className="font-mono text-[10.5px] tracking-[0.08em] text-subtle">RESPONSE HEADERS</p>
          <dl className="mt-4 grid gap-3 font-mono text-[11.5px]">
            {RESPONSE_HEADERS.map(([name, value, highlight]) => (
              <div key={name} className="flex justify-between gap-3">
                <dt className="text-muted">{name}</dt>
                <dd className={cn("truncate", highlight ? "text-accent-text" : "text-ink")}>{value}</dd>
              </div>
            ))}
          </dl>

          <div className="mt-6 h-px bg-line" />

          <p className="mt-6 font-mono text-[10.5px] tracking-[0.08em] text-subtle">STREAM</p>
          <div className="mt-3.5 grid gap-2 font-mono text-[11px] text-muted">
            <div>data: {'{"delta":"Ref"}'}</div>
            <div>data: {'{"delta":"actor"}'}</div>
            <div>data: {'{"delta":"ing"}'}</div>
            <div className="text-subtle">data: [DONE]</div>
          </div>
        </div>
      </div>
    </div>
  )
}
