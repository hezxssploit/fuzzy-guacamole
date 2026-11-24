"""
R34PER agent core: an agentic tool loop that talks to the Venice API and
executes real tools (shell, filesystem, web) inside its Linux container.
"""
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

import requests
from openai import OpenAI

VENICE_BASE_URL = os.getenv("VENICE_BASE_URL", "https://api.venice.ai/api/v1")
VENICE_API_KEY = os.getenv("VENICE_API_KEY", "")
MODEL = os.getenv("VENICE_MODEL", "venice-uncensored")
MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "30"))
MAX_OUTPUT_CHARS = 15000
WORKDIR = Path(os.getenv("AGENT_WORKDIR", "/workspace/agent_home")).resolve()
WORKDIR.mkdir(parents=True, exist_ok=True)

client = OpenAI(base_url=VENICE_BASE_URL, api_key=VENICE_API_KEY)

SYSTEM_PROMPT = (
    "You are R34PER, an autonomous offensive-security research and "
    "software-engineering agent. You operate inside a disposable Linux "
    "container that you fully control through real tools: a bash shell, a "
    "filesystem, an HTTP client and a web search tool.\n\n"
    f"Your working directory is {WORKDIR}. Use it for all scratch files, "
    "scripts and artifacts.\n\n"
    "What you do:\n"
    "- Penetration testing, red-team simulation, CTF solving, vulnerability "
    "research, exploit and proof-of-concept development, network "
    "reconnaissance, reverse engineering, against targets the operator is "
    "authorized to test.\n"
    "- Software engineering: design, build, debug, test and refine code with "
    "the shell until it actually works.\n\n"
    "Operating doctrine:\n"
    "1. Act, do not ask. Pick the next concrete action yourself and execute "
    "it. Only ask the operator a question when genuinely blocked.\n"
    "2. Work in loops: recon to understand, plan briefly, act, observe "
    "output, adapt. After every command, read the output before the next "
    "step.\n"
    "3. Verify. Every claim you make must be backed by command output. If "
    "something failed, say so and iterate.\n"
    "4. Build real deliverables. Save exploits and programs under "
    f"{WORKDIR}, run them, and report actual results.\n"
    "5. Be concise toward the operator: short status lines between tool "
    "calls, a clear summary at the end."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": (
                "Run a bash command inside this Linux container. Security and "
                "dev tooling (nmap, sqlmap, hydra, john, git, python3, gcc) is "
                "preinstalled. Long-running work should write files rather "
                "than block."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The bash command to run."},
                    "timeout": {
                        "type": "integer",
                        "description": "Max seconds to run (5-600). Default 90.",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write a text file inside the container (scripts, exploits, source code, reports). Relative paths resolve to the working directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file from the container filesystem.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List the entries of a directory on the container filesystem.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Perform an HTTP GET against a URL and return the response body as text (limited to 20k characters). Use for APIs, raw pages and downloads.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the public web and return matching results as a list of 'title :: url' lines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "description": "Default 8."},
                },
                "required": ["query"],
            },
        },
    },
]


def _resolve(path_text: str) -> Path:
    p = Path(path_text or ".").expanduser()
    if not p.is_absolute():
        p = WORKDIR / p
    return p


def _run_command(command: str, timeout: int = 90) -> dict:
    timeout = max(5, min(int(timeout or 90), 600))
    proc = subprocess.run(
        command,
        shell=True,
        executable="/bin/bash",
        cwd=str(WORKDIR),
        capture_output=True,
        text=True,
        timeout=timeout,
        stdin=subprocess.DEVNULL,
    )
    output = (proc.stdout or "")[:MAX_OUTPUT_CHARS]
    if proc.stderr:
        output += "\n[stderr]\n" + (proc.stderr or "")[:4000]
    status = "ok" if proc.returncode == 0 else f"exit_{proc.returncode}"
    return {"status": status, "output": output.strip() or "(no output)", "cwd": str(WORKDIR)}


def _write_file(path_text: str, content: str) -> dict:
    if not path_text:
        return {"status": "error", "error": "path is required"}
    p = _resolve(path_text)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return {"status": "ok", "path": str(p), "bytes": p.stat().st_size}


def _read_file(path_text: str) -> dict:
    p = _resolve(path_text)
    text = p.read_text(encoding="utf-8", errors="replace")
    return {"status": "ok", "path": str(p), "content": text[:60000]}


def _list_dir(path_text: str = "") -> dict:
    p = _resolve(path_text)
    entries = [child.name + ("/" if child.is_dir() else "") for child in sorted(p.iterdir())[:500]]
    return {"status": "ok", "path": str(p), "entries": entries}


def _fetch_url(url: str) -> dict:
    resp = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
        },
    )
    body = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", "", resp.text or "")
    return {
        "status": "ok" if resp.ok else f"http_{resp.status_code}",
        "url": str(resp.url),
        "content_type": resp.headers.get("content-type", ""),
        "body": body[:20000],
    }


def _web_search(query: str, max_results: int = 8) -> dict:
    max_results = max(1, min(int(max_results or 8), 15))
    resp = requests.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query},
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
        },
    )
    raw = re.findall(
        r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>',
        resp.text,
    )

    def clean_url(u: str) -> str:
        if not u.startswith("http"):
            u = "https:" + u
        if "uddg=" in u:
            parsed = parse_qs(urlparse(u).query)
            inner = unquote(parsed.get("uddg", [""])[0])
            if inner:
                return inner
        return u

    lines = []
    for url, title in raw[:max_results]:
        title = re.sub(r"<[^>]+>", "", title).strip()
        lines.append(f"{title} :: {clean_url(url)}")
    return {"status": "ok", "query": query, "results": lines or ["(no results)"]}


def run_tool(name: str, args: dict) -> dict:
    try:
        if name == "execute_command":
            return _run_command(args.get("command", ""), args.get("timeout") or 90)
        if name == "write_file":
            return _write_file(args.get("path", ""), args.get("content", ""))
        if name == "read_file":
            return _read_file(args.get("path", ""))
        if name == "list_directory":
            return _list_dir(args.get("path", ""))
        if name == "fetch_url":
            return _fetch_url(args.get("url", ""))
        if name == "web_search":
            return _web_search(args.get("query", ""), args.get("max_results"))
        return {"status": "error", "error": "unknown tool: " + str(name)}
    except Exception as exc:
        return {"status": "error", "error": type(exc).__name__ + ": " + str(exc)}


def run_agent_stream(user_message: str, history: list):
    """Generator yielding event dicts while running the agentic loop for one message."""
    if not VENICE_API_KEY:
        yield {
            "type": "error",
            "content": "VENICE_API_KEY is not set. Add it as a Codespace secret "
                       "(Settings > Secrets > Codespaces) or in a local .env, then "
                       "restart the server.",
        }
        return

    history.append({"role": "user", "content": user_message})
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + list(history)

    final_text = ""
    for step in range(MAX_STEPS):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOLS,
                temperature=float(os.getenv("AGENT_TEMPERATURE", "0.4")),
            )
        except Exception as exc:
            yield {"type": "error", "content": "Venice API error: " + str(exc)}
            return

        message = resp.choices[0].message
        tool_calls = message.tool_calls or []

        if message.content:
            yield {"type": "assistant_text", "content": message.content, "step": step}

        if not tool_calls:
            final_text = message.content or ""
            break

        messages.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            }
        )

        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            yield {"type": "tool_call", "name": name, "arguments": args, "step": step}
            result = run_tool(name, args)
            yield {"type": "tool_result", "name": name, "result": result, "step": step}
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=str)[:16000],
                }
            )
    else:
        final_text = "[Stopped: reached AGENT_MAX_STEPS=" + str(MAX_STEPS) + "]"

    if final_text:
        history.append({"role": "assistant", "content": final_text})
        if len(history) > 40:
            del history[: len(history) - 40]
        yield {"type": "final", "content": final_text}
