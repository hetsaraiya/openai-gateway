RETRYABLE_UPSTREAM_STATUSES = frozenset({429, 500, 502, 503, 504})

CODEX_SUPPORTED_ENDPOINTS = ("/v1/responses", "/v1/chat/completions")

OPENCODE_GO_MODEL_PREFIX = "opencode-go/"
OPENCODE_GO_CHAT_ENDPOINT = "/v1/chat/completions"
OPENCODE_GO_MESSAGES_ENDPOINT = "/v1/messages"
OPENCODE_GO_MESSAGES_MODELS = frozenset(
    {
        "minimax-m3",
        "minimax-m2.7",
        "minimax-m2.5",
        "qwen3.7-max",
        "qwen3.7-plus",
        "qwen3.6-plus",
    }
)

XAI_MODEL_PREFIX = "xai/"
XAI_SUPPORTED_ENDPOINTS = ("/v1/chat/completions", "/v1/responses")
