# MCP client registration

DevMemoryIndex exposes a stdio MCP server through the `devmemory-mcp-server` command. The safest automated setup pattern is to use a stable wrapper script and a deterministic client config entry instead of relying on activated shells or interactive prompts.

## Hermes Agent: non-interactive install

Use the DevMemoryIndex CLI helper when the setup must run from an agent, bootstrap script, or CI job:

```bash
devmemory mcp install-hermes --yes
hermes mcp test devmemory
```

Preview without writing files:

```bash
devmemory mcp install-hermes --dry-run
```

Useful options:

```bash
devmemory mcp install-hermes \
  --yes \
  --wrapper-path ~/.local/bin/devmemory-mcp-server \
  --hermes-config ~/.hermes/config.yaml \
  --repo-dir /path/to/devmemoryindex \
  --timeout 120 \
  --connect-timeout 60
```

The command writes:

1. A stable wrapper at `~/.local/bin/devmemory-mcp-server`.
2. A `mcp_servers.devmemory` entry in the Hermes config.

Restart Hermes or run `/reload-mcp` after applying the change. Then verify:

```bash
hermes mcp test devmemory
```

Expected result: Hermes connects to the stdio server and discovers the DevMemoryIndex MCP tools.

## Why use a wrapper?

A wrapper keeps MCP client setup predictable:

- avoids depending on shell aliases or an activated virtualenv;
- pins the working directory before running `python -m mcp_server.server`;
- avoids argument parsing ambiguity in clients that split command/args differently;
- gives every MCP client a single executable path to run.

Example wrapper:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd /path/to/devmemoryindex
exec /path/to/devmemoryindex/.venv/bin/python -m mcp_server.server
```

## Manual Hermes config block

If you prefer to manage Hermes config yourself, add:

```yaml
mcp_servers:
  devmemory:
    command: "/home/you/.local/bin/devmemory-mcp-server"
    args: []
    timeout: 120
    connect_timeout: 60
```

## Claude Code / generic MCP stdio config

For MCP clients that accept JSON-style stdio server definitions, use the same wrapper command:

```json
{
  "mcpServers": {
    "devmemory": {
      "command": "/home/you/.local/bin/devmemory-mcp-server",
      "args": []
    }
  }
}
```

## Troubleshooting

- If the client reports `No module named 'mcp'`, install DevMemoryIndex with the MCP extra in the environment used by the wrapper:

  ```bash
  uv pip install -e '.[mcp]'
  ```

- If Hermes connects but tools do not appear, restart Hermes or run `/reload-mcp`.
- If the command works in your shell but not in Hermes, check that the wrapper uses absolute paths and does not rely on shell activation.
