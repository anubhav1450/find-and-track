# Architecture

The local release has one Python process serving static HTML/CSS/JavaScript and JSON APIs on loopback. There is no frontend build step. Python 3.11+ and pypdf are enough for the runtime.

- `server.py`: request validation, origin/token protection and SQLite workspace persistence with optimistic revision checks.
- `workflow.py`: profile rules, screening, employer discovery, deduplication and tracking preparation.
- `startup_sources.py`: Ashby feed normalization; Greenhouse/Lever/Remotive adapters live in workflow.
- `job_import.py`: supported posting URL import using fixed public API endpoints.
- `web_discovery.py`: role-first indexed discovery and posting-link previews.
- `company_research.py`: company evidence, affiliation screening and contact deduplication.
- `search_provider.py`: optional Tavily credentials, bounded responses, six-hour cache and local request cap.
- `static/app.js` and `static/domain.js`: UI orchestration and domain operations.
- `cloud.py`: optional owner-authenticated Supabase adapter. Local and cloud workspaces do not sync.

## Evidence boundaries

Publication time, first-seen time and checked time are separate. Search leads remain unconfirmed until verified against an employer source. Feed failures preserve records; successful feed absence is represented without deleting application history. Company reports collect evidence, not definitive fraud judgments. Contact links do not prove current employment, activity or ownership of a vacancy.

## Data flow

Resume extraction is local. Employer adapters send feed requests; Tavily receives role/location queries, company queries and posting URLs. No full resume is sent by the search integration. Application/contact state remains local unless the owner explicitly uses a cloud deployment or exports it.

## Release scope

This release is single-user and local-first. Multi-user hosting, durable shared search quotas, scheduled discovery and Gmail OAuth need separate design and verification. The local HTTP server must not be exposed directly to the internet.
