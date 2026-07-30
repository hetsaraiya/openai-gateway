# Claude consumer subscriptions and API access

Research checked against Anthropic's official documentation on 30 July 2026.

## Conclusion

A Claude Pro, Max, Team, or Enterprise subscription is not a general-purpose
Claude API entitlement. This gateway should integrate Claude through an
Anthropic Console API key (or a supported cloud provider such as Amazon Bedrock,
Google Vertex AI, or Microsoft Foundry) with separate usage billing.

Do not reuse Claude web or Claude Code OAuth/session credentials to proxy shared
gateway traffic. Anthropic says third-party products should use API-key
authentication and explicitly prohibits tools that misrepresent their identity
or route third-party traffic against subscription limits.

## Important distinction

Anthropic permits subscription authentication for its native applications,
including interactive Claude Code. As of the research date, Anthropic also says
that Claude Agent SDK, `claude -p`, and some third-party Agent SDK usage may draw
from an individual subscription's limits while a planned billing change is
paused. That is a product-specific, per-user path; it does not turn a consumer
subscription into a standard Messages API key and is not suitable as shared
gateway infrastructure.

Usage credits available to Claude subscribers are also separate charges at
standard API rates. They do not make the subscription's included chat allowance
available through the standard API.

## Recommended integration

1. Create or use an Anthropic Console organization and enable billing.
2. Store an Anthropic API key as a backend credential.
3. Add an Anthropic provider strategy targeting the documented Messages API.
4. Keep credentials server-side and apply the gateway's existing account,
   quota, retry, and API-safe-variable policies.

## Official sources

- [Claude subscription and API/Console are separate products](https://support.claude.com/en/articles/9876003-i-have-a-paid-claude-subscription-pro-max-team-or-enterprise-plans-why-do-i-have-to-pay-separately-to-use-the-claude-api-and-console)
- [Third-party tools should use Console API keys or supported cloud providers](https://support.claude.com/en/articles/13189465-log-in-to-your-claude-account)
- [Claude API usage uses prepaid Console credits](https://support.claude.com/en/articles/8977456-how-do-i-pay-for-my-claude-api-usage)
- [Current Agent SDK subscription exception and paused billing change](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan)
