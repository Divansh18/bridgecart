# Runbook: foundation

For API process status, request `/health/live`. For database reachability, request `/health/ready`; a 503 means PostgreSQL is unavailable or the configured deadline elapsed. Check the JSON logs on stdout and verify `BRIDGECART_DATABASE_URL`, credentials, database availability, and network path. Never paste the full database URL into incident tickets or logs.

For local MCP service checks, connect an MCP client to each `/mcp` URL and list tools. An empty list is expected at this milestone. There is no authenticated tool execution or cluster deployment to operate yet.
