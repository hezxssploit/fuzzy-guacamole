# R34PER Agent

Uncensored AI hacking + coding agent with a full Linux attack environment and a chat UI, powered by your Venice API key.

- **Brain:** Venice API (OpenAI-compatible, uncensored models) via your own key.
- **Body:** a Kali Linux container running real commands, real files, real network tools.
- **Chat UI:** single-page terminal-styled web interface with live streaming of every step.
- **Desktop (optional):** full XFCE desktop in the browser over noVNC.

## What it can do

| Tool | Effect |
| --- | --- |
| execute_command | Real bash in the container (nmap, sqlmap, hydra, john, gcc, python3...) |
| write_file / read_file / list_directory | Full filesystem access in the container |
| fetch_url | HTTP GET any URL, body returned to the model |
| web_search | Free DuckDuckGo search, results fed to the model |

The agent loops: think, call tools, observe, adapt, up to AGENT_MAX_STEPS (default 30) rounds per message, streaming each step to your browser.

## Quickstart: GitHub Codespaces (free, no local machine needed)

1. Add repository secret VENICE_API_KEY: Settings > Secrets and variables > Codespaces.
2. Open a Codespace (Code button > Codespaces > Create codespace). The devcontainer builds the Kali image and auto-starts the server on port 8000.
3. Open port 8000. Chat.

Optional browser desktop:

    bash scripts/desktop.sh
    # open forwarded port 6080, append /vnc.html

## Quickstart: local Docker

    cp .env.example .env    # put your Venice key in it
    docker compose up --build
    # open http://localhost:8000

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| VENICE_API_KEY | (required) | Your API key from venice.ai settings |
| VENICE_MODEL | venice-uncensored | Any model id from GET /models |
| VENICE_BASE_URL | https://api.venice.ai/api/v1 | Swap for any OpenAI-compatible endpoint |
| AGENT_MAX_STEPS | 30 | Max tool rounds per user message |
| AGENT_WORKDIR | /workspace/agent_home | Agent scratch directory |
| VNC_PASSWORD | hacktheplanet | noVNC desktop password |

## List available models

    curl https://api.venice.ai/api/v1/models -H "Authorization: Bearer $VENICE_API_KEY"

Note: tool-calling support varies per model. If the agent never runs tools, switch model. Usage is billed per token; there is no free Venice API tier.

## Security model

Everything the agent executes stays inside the container. When operating outside a throwaway environment, restrict the container network, never store real credentials inside it, and keep secrets in environment variables only.

## Legal notice

This software is for security research and education on systems you own or have explicit written authorization to test. Operating it against third-party systems without authorization is illegal. The author accepts no liability.

## License

MIT.
