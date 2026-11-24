# Security and privacy

Run the local server on its default loopback address. It is not a public internet server. Optional hosting requires the authentication and row-level security described in DEPLOYMENT.md.

Never commit resumes, API keys, workspace databases, search caches, email batches or exported backups. The data directory and environment files are ignored. Keep personal backups outside the repository. The Tavily key is server-side and excluded from workspace exports; local credential/database files use owner-only permissions.

Optional search sends query terms and posting URLs to Tavily. Opening external links exposes normal browser request information to those sites. Company reports and public profile snippets may be outdated; verify before acting.

For a suspected vulnerability, use GitHub private vulnerability reporting if enabled on the repository. Otherwise open an issue requesting a private contact channel without including exploit details, tokens or personal data. Do not post credentials in public issues. Revoke any accidentally exposed key with its provider.

Only the latest release is maintained. There is no response-time guarantee for this volunteer project.
