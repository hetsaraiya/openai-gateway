/**
 * Schematic diagrams for the landing page. Each one is a plain SVG inked with
 * the console's theme variables so it follows light and dark, plus a dashed
 * overlay and a travelling dot that suggest a request moving through the
 * gateway. The figures are illustrative, not a live read of a deployment.
 */

/** Duration of one packet traversal, in seconds. */
const SLOW = 2.8
const FAST = 1.6

const line = { stroke: "var(--line)" }
const lineStrong = { stroke: "var(--line-strong)" }
const surface = { fill: "var(--surface)", stroke: "var(--line)" }
const accent = "var(--accent)"

/** A dot that rides `path` on repeat, delayed so parallel edges stay offset. */
function Packet({ path, dur, begin = 0, r = 3, fill = accent }: { path: string; dur: number; begin?: number; r?: number; fill?: string }) {
  return (
    <circle r={r} fill={fill}>
      <animateMotion dur={`${dur}s`} begin={`${begin}s`} repeatCount="indefinite" path={path} />
    </circle>
  )
}

/** The animated blue dashes that trace an edge underneath the packet. */
function Flow({ path, dur = 3, begin = 0, gap = 116 }: { path: string; dur?: number; begin?: number; gap?: number }) {
  return (
    <path
      d={path}
      fill="none"
      stroke={accent}
      strokeWidth={1.2}
      strokeDasharray={`4 ${gap}`}
      opacity={0.85}
      style={{ animation: `edge-dash ${dur}s linear infinite`, animationDelay: `${begin}s` }}
    />
  )
}

const HERO_EDGES = {
  ide: "M100 66 C100 122 310 114 310 170",
  cli: "M310 66 L310 170",
  ci: "M520 66 C520 122 310 114 310 170",
  router: "M310 266 L310 330",
  codex: "M310 394 C310 442 88 424 88 470",
  cursor: "M310 394 C310 442 236 430 236 470",
  grok: "M310 394 C310 442 384 430 384 470",
  opencode: "M310 394 C310 442 532 424 532 470",
}

type Upstream = { x: number; label: string; auth: string; state: string; fill: number; healthy: boolean }

// Cards are 136 wide with a 16 inset, so `auth` and `state` have ~104 to run in.
// At 10.5px monospace that is about 16 characters — keep both lines under it.
const UPSTREAMS: Upstream[] = [
  { x: 20, label: "Codex", auth: "oauth · files", state: "healthy", fill: 82, healthy: true },
  { x: 168, label: "Cursor", auth: "cursor-agent", state: "healthy", fill: 58, healthy: true },
  { x: 316, label: "Grok", auth: "device oauth", state: "cooldown 41s", fill: 96, healthy: false },
  { x: 464, label: "OpenCode", auth: "subscription key", state: "healthy", fill: 34, healthy: true },
]

/** Hero figure: clients above, the gateway and router in the middle, upstream accounts below. */
export function TopologyDiagram() {
  return (
    <svg viewBox="0 -6 620 592" width="100%" className="block overflow-visible font-sans" aria-label="Clients reach four upstream account pools through one gateway">
      <g style={line} strokeWidth={1.2} fill="none">
        {Object.values(HERO_EDGES).map((d) => (
          <path key={d} d={d} />
        ))}
      </g>

      <g>
        <Flow path={HERO_EDGES.ide} dur={3.2} />
        <Flow path={HERO_EDGES.cli} dur={3.2} begin={0.9} />
        <Flow path={HERO_EDGES.ci} dur={3.2} begin={1.7} />
        <Flow path={HERO_EDGES.router} dur={1.6} />
        <Flow path={HERO_EDGES.codex} dur={3} begin={0.3} />
        <Flow path={HERO_EDGES.cursor} dur={3} begin={1.1} />
        <Flow path={HERO_EDGES.grok} dur={3} begin={1.9} />
        <Flow path={HERO_EDGES.opencode} dur={3} begin={2.5} />
      </g>

      <g>
        <Packet path={HERO_EDGES.ide} dur={SLOW} />
        <Packet path={HERO_EDGES.ci} dur={SLOW} begin={1.1} />
        <Packet path={HERO_EDGES.router} dur={FAST} r={2.6} />
        <Packet path={HERO_EDGES.codex} dur={SLOW} begin={0.4} r={2.6} />
        <Packet path={HERO_EDGES.grok} dur={SLOW} begin={1.6} r={2.6} />
      </g>

      <g>
        <text x={20} y={14} className="font-mono" fontSize={10.5} letterSpacing="0.08em" fill="var(--subtle)">
          CLIENT APPLICATIONS
        </text>
        {[
          { x: 40, label: "IDE / editor" },
          { x: 250, label: "CLI agents" },
          { x: 460, label: "CI pipelines" },
        ].map((client) => (
          <g key={client.label}>
            <rect x={client.x} y={30} width={120} height={36} rx={9} style={surface} />
            <text x={client.x + 60} y={53} textAnchor="middle" fontSize={12.5} fill="var(--muted)">
              {client.label}
            </text>
          </g>
        ))}
      </g>

      <g>
        <rect x={140} y={170} width={340} height={96} rx={14} style={surface} />
        <rect x={140} y={170} width={340} height={96} rx={14} fill={accent} opacity={0.03} />
        <text x={164} y={200} fontSize={15} fontWeight={600} fill="var(--ink)">
          Gateway
        </text>
        <text x={164} y={220} className="font-mono" fontSize={11.5} fill="var(--muted)">
          :8000/v1
        </text>
        <circle cx={452} cy={192} r={3.5} fill={accent} style={{ animation: "node-pulse 1.8s ease-in-out infinite" }} />
        <text x={440} y={196} textAnchor="end" className="font-mono" fontSize={11} fill="var(--muted)">
          streaming
        </text>
        <line x1={164} y1={238} x2={456} y2={238} stroke="var(--line)" />
        <text x={164} y={256} className="font-mono" fontSize={11} fill="var(--muted)">
          chat · responses
        </text>
        <text x={456} y={256} textAnchor="end" className="font-mono" fontSize={11} fill="var(--accent-text)">
          idempotency cache
        </text>
      </g>

      <g>
        <rect x={190} y={330} width={240} height={64} rx={12} style={surface} />
        <text x={310} y={356} textAnchor="middle" fontSize={13.5} fontWeight={600} fill="var(--ink)">
          Account router
        </text>
        <text x={310} y={376} textAnchor="middle" className="font-mono" fontSize={11} fill="var(--muted)">
          fallback · round robin · quota
        </text>
      </g>

      <g>
        <text x={20} y={454} className="font-mono" fontSize={10.5} letterSpacing="0.08em" fill="var(--subtle)">
          UPSTREAM ACCOUNTS
        </text>
        {UPSTREAMS.map((upstream) => (
          <g key={upstream.label}>
            <rect x={upstream.x} y={470} width={136} height={104} rx={12} style={surface} />
            <circle cx={upstream.x + 16} cy={492} r={3.5} fill={upstream.healthy ? accent : "var(--line-strong)"} />
            <text x={upstream.x + 28} y={496} fontSize={12.5} fontWeight={600} fill="var(--ink)">
              {upstream.label}
            </text>
            <text x={upstream.x + 16} y={522} className="font-mono" fontSize={10.5} fill="var(--muted)">
              {upstream.auth}
            </text>
            <text x={upstream.x + 16} y={540} className="font-mono" fontSize={10.5} fill={upstream.healthy ? "var(--muted)" : "var(--subtle)"}>
              {upstream.state}
            </text>
            <rect x={upstream.x + 16} y={552} width={104} height={4} rx={2} fill="var(--inset)" />
            <rect x={upstream.x + 16} y={552} width={(upstream.fill * 104) / 100} height={4} rx={2} fill={upstream.healthy ? accent : "var(--line-strong)"} />
          </g>
        ))}
      </g>
    </svg>
  )
}

const PIPELINE_EDGES = ["M196 120 L262 120", "M414 120 L480 120", "M632 120 L698 120", "M916 120 L982 120"]
const RETURN_EDGE = "M1050 168 C1050 236 200 236 200 176"

/** Architecture figure: the request path from client to provider and back. */
export function PipelineDiagram() {
  return (
    <svg viewBox="0 46 1120 232" width="100%" className="block font-sans" aria-label="Request pipeline from client to provider and back">
      <g style={line} strokeWidth={1.2} fill="none">
        {PIPELINE_EDGES.map((d) => (
          <path key={d} d={d} />
        ))}
        <path d={RETURN_EDGE} strokeDasharray="5 6" />
      </g>

      <g>
        {PIPELINE_EDGES.map((d, index) => (
          <Flow key={d} path={d} dur={2} begin={index * 0.3} gap={62} />
        ))}
      </g>

      <g>
        {PIPELINE_EDGES.map((d, index) => (
          <Packet key={d} path={d} dur={FAST} begin={index * 0.5} />
        ))}
        <Packet path={RETURN_EDGE} dur={4.4} r={2.6} fill="var(--line-strong)" />
      </g>

      <g>
        <rect x={60} y={88} width={136} height={64} rx={12} style={surface} />
        <text x={128} y={114} textAnchor="middle" fontSize={13.5} fontWeight={600} fill="var(--ink)">
          Clients
        </text>
        <text x={128} y={134} textAnchor="middle" className="font-mono" fontSize={10.5} fill="var(--subtle)">
          sdk · cli · ide
        </text>

        <rect x={262} y={88} width={152} height={64} rx={12} style={surface} />
        <text x={338} y={114} textAnchor="middle" fontSize={13.5} fontWeight={600} fill="var(--ink)">
          Gateway
        </text>
        <text x={338} y={134} textAnchor="middle" className="font-mono" fontSize={10.5} fill="var(--subtle)">
          auth · dedup
        </text>

        <rect x={480} y={88} width={152} height={64} rx={12} style={surface} />
        <text x={556} y={114} textAnchor="middle" fontSize={13.5} fontWeight={600} fill="var(--ink)">
          Router
        </text>
        <text x={556} y={134} textAnchor="middle" className="font-mono" fontSize={10.5} fill="var(--subtle)">
          quota · health
        </text>

        <rect x={698} y={62} width={218} height={116} rx={12} style={surface} />
        <text x={718} y={86} fontSize={13.5} fontWeight={600} fill="var(--ink)">
          Providers
        </text>
        <text x={718} y={112} className="font-mono" fontSize={10.5} fill="var(--muted)">
          codex · cursor
        </text>
        <text x={718} y={132} className="font-mono" fontSize={10.5} fill="var(--muted)">
          grok · opencode go
        </text>
        <circle cx={896} cy={82} r={3.5} fill={accent} style={{ animation: "node-pulse 2s ease-in-out infinite" }} />
        <rect x={718} y={150} width={178} height={4} rx={2} fill="var(--inset)" />
        <rect x={718} y={150} width={124} height={4} rx={2} fill={accent} />

        <rect x={982} y={88} width={136} height={64} rx={12} style={surface} />
        <text x={1050} y={114} textAnchor="middle" fontSize={13.5} fontWeight={600} fill="var(--ink)">
          Responses
        </text>
        <text x={1050} y={134} textAnchor="middle" className="font-mono" fontSize={10.5} fill="var(--subtle)">
          sse stream
        </text>

        <text x={560} y={262} textAnchor="middle" className="font-mono" fontSize={10.5} letterSpacing="0.08em" fill="var(--subtle)">
          TOKENS STREAMED BACK ON THE SAME CONNECTION
        </text>
      </g>
    </svg>
  )
}

const BENCHED = "M150 74 C240 74 240 150 300 150"
const RETRIED = "M150 266 C240 266 240 178 300 178"
const SERVED = "M420 164 L500 164"

/** Routing figure: a rate-limited account is skipped and the retry succeeds. */
export function FailoverDiagram() {
  return (
    <svg viewBox="8 14 624 296" width="100%" className="block font-sans" aria-label="A rate-limited account is skipped and the request is retried on a healthy one">
      <g style={line} strokeWidth={1.2} fill="none">
        <path d={BENCHED} />
        <path d={RETRIED} />
        <path d={SERVED} />
      </g>

      <path d={BENCHED} fill="none" strokeWidth={1.4} strokeDasharray="4 5" style={lineStrong} />
      <Flow path={RETRIED} dur={2.2} gap={64} />
      <Flow path={SERVED} dur={1.6} gap={64} />

      <Packet path={RETRIED} dur={2.4} />
      <Packet path={SERVED} dur={FAST} begin={0.8} />

      <g>
        <text x={20} y={26} className="font-mono" fontSize={10.5} letterSpacing="0.08em" fill="var(--subtle)">
          429 → COOLDOWN → RETRY
        </text>

        <rect x={20} y={44} width={130} height={60} rx={11} style={surface} />
        <text x={38} y={70} fontSize={12.5} fontWeight={600} fill="var(--ink)">
          Account A
        </text>
        <circle cx={38} cy={86} r={3} fill="var(--line-strong)" />
        <text x={48} y={90} className="font-mono" fontSize={10.5} fill="var(--subtle)">
          cooldown 41s
        </text>

        <rect x={20} y={236} width={130} height={60} rx={11} style={surface} />
        <text x={38} y={262} fontSize={12.5} fontWeight={600} fill="var(--ink)">
          Account B
        </text>
        <circle cx={38} cy={278} r={3} fill={accent} style={{ animation: "node-pulse 1.8s ease-in-out infinite" }} />
        <text x={48} y={282} className="font-mono" fontSize={10.5} fill="var(--muted)">
          healthy
        </text>

        <rect x={300} y={128} width={120} height={72} rx={12} style={surface} />
        <text x={360} y={158} textAnchor="middle" fontSize={13} fontWeight={600} fill="var(--ink)">
          Gateway
        </text>
        <text x={360} y={178} textAnchor="middle" className="font-mono" fontSize={10.5} fill="var(--muted)">
          attempt 2 / 3
        </text>

        <rect x={500} y={134} width={126} height={60} rx={11} style={surface} />
        <text x={563} y={160} textAnchor="middle" fontSize={12.5} fontWeight={600} fill="var(--ink)">
          200 OK
        </text>
        <text x={563} y={178} textAnchor="middle" className="font-mono" fontSize={10.5} fill="var(--accent-text)">
          streamed
        </text>

        <text x={168} y={160} className="font-mono" fontSize={10.5} fill="var(--line-strong)">
          skipped
        </text>
      </g>
    </svg>
  )
}

const CREDENTIAL_EDGES = ["M186 110 L266 110", "M414 110 L494 110", "M690 110 L770 110", "M918 110 L998 110"]

/** Security figure: where each credential lives along the request path. */
export function CredentialDiagram() {
  return (
    <svg viewBox="46 58 1084 104" width="100%" className="block font-sans" aria-label="Credential flow from client key to upstream token">
      <g style={line} strokeWidth={1} fill="none">
        {CREDENTIAL_EDGES.map((d) => (
          <path key={d} d={d} />
        ))}
      </g>
      <g>
        {CREDENTIAL_EDGES.map((d, index) => (
          <Flow key={d} path={d} dur={2.4} begin={index * 0.4} gap={60} />
        ))}
      </g>

      <g fill="none">
        <rect x={60} y={80} width={126} height={60} rx={10} style={surface} />
        <rect x={78} y={102} width={12} height={9} rx={2} stroke={accent} strokeWidth={1.1} />
        <path d="M80.5 102v-2.5a3.5 3.5 0 0 1 7 0V102" stroke={accent} strokeWidth={1.1} />
        <text x={98} y={112} fontSize={12} fontWeight={600} fill="var(--ink)">
          Client key
        </text>
        <text x={78} y={130} className="font-mono" fontSize={10} fill="var(--subtle)">
          GATEWAY_API_KEY
        </text>

        <rect x={266} y={80} width={148} height={60} rx={10} style={surface} />
        <text x={340} y={106} textAnchor="middle" fontSize={12.5} fontWeight={600} fill="var(--ink)">
          Gateway
        </text>
        <text x={340} y={124} textAnchor="middle" className="font-mono" fontSize={10} fill="var(--subtle)">
          verify · route
        </text>

        <rect x={494} y={72} width={196} height={76} rx={10} style={surface} />
        <text x={592} y={102} textAnchor="middle" fontSize={12.5} fontWeight={600} fill="var(--ink)">
          Credential files
        </text>
        <text x={592} y={122} textAnchor="middle" className="font-mono" fontSize={10} fill="var(--subtle)">
          auth/ · 0700 · on your disk
        </text>
        <path d="M520 134h144" stroke="var(--line)" />

        <rect x={770} y={80} width={148} height={60} rx={10} style={surface} />
        <text x={844} y={106} textAnchor="middle" fontSize={12.5} fontWeight={600} fill="var(--ink)">
          Providers
        </text>
        <text x={844} y={124} textAnchor="middle" className="font-mono" fontSize={10} fill="var(--subtle)">
          https only
        </text>

        <rect x={998} y={80} width={122} height={60} rx={10} style={surface} />
        <text x={1059} y={106} textAnchor="middle" fontSize={12.5} fontWeight={600} fill="var(--ink)">
          Responses
        </text>
        <text x={1059} y={124} textAnchor="middle" className="font-mono" fontSize={10} fill="var(--subtle)">
          no body logging
        </text>
      </g>
    </svg>
  )
}
