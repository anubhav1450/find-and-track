# Resume-driven discovery v0.2

## Product decision: search by role

A user imports a resume and taps Find jobs. Derive target titles from saved preferences and skills, search across employers, inspect responsibilities and eligibility, then rank by resume evidence. A company list is optional supplemental coverage. Keep an unverified lead in Needs review until the original employer confirms the opening. Preserve provider attribution and application progress across searches.

First slice: search the Remotive software catalog locally using derived role terms, with a six-hour process cache. Remote coverage only. Supplemental Lever boards still provide direct postings. Next slice: broader India onsite/hybrid sources, JD-based handling of ambiguous titles, employer verification and screening corrections. Evaluate live yield and manually review accepted and rejected jobs before calling the milestone complete.

## Outcome
Import a resume, confirm extracted skills and search preferences, press Find jobs, and receive current employer postings ranked against that profile. Each result links to its source and explains matches, gaps and uncertainty.

## Current implementation audit
The workflow fetches only Hevo's Lever board. Screening is hard-coded to Indian fresher software roles. Resume preparation follows retrieval but the imported profile does not drive source selection or eligibility screening. Existing URL matching preserves application progress on refresh.

## Source strategy
Start with configured employer boards using the documented Lever Postings API and Greenhouse Job Board API. These endpoints operate per employer, so a maintained employer registry is necessary for coverage. Confirm intended use and applicable terms for each source before enabling it. Public accessibility alone is not permission for unrestricted aggregation. Fetch on demand with bounded responses, timeouts, caching and per-source failure reporting. Show supported coverage and last checked time. Wider employer discovery is a separate coverage task.

References:
- https://github.com/lever/postings-api
- https://docs.greenhouse.io/job-board

## Ralph Loop tasks and exit conditions
1. Profile-driven screening. Introduce explicit editable role families, geography and experience preferences. Preserve legacy personal defaults for existing workspaces. Pass when two different profiles produce appropriately different decisions for the same fixtures, and ambiguous criteria remain reviewable.
2. Multiple employer feeds. Normalize Lever and Greenhouse postings into a common record with provider ID, employer, canonical posting URL, JD and checked time. Pass when pagination and partial failures are handled and no failed fetch marks jobs closed.
3. Ranked discovery in the dashboard. Use verified resume skills and eligibility preferences. Explain ranking with evidence, keep unknown compensation visible, and avoid interpreting advertised gross pay as take-home. Pass when a normal Find jobs action retrieves and displays source-backed matches.
4. Repeat-search safety. Update source details while preserving application status, notes and contacts. Pass when repeated searches do not duplicate provider records and cross-source uncertainty is flagged rather than incorrectly merged.
5. Live acceptance. Run against a documented small employer set, manually review relevance and eligibility, record source coverage, latency and rejection reasons. Report zero matches honestly. Expand coverage based on measured results.

For each task: implement one slice, run its checks, fix failures, record evidence, then move to the next. Keep progress in this document. No Ralph automation package is installed yet; this is the explicit manual iteration contract.

## Boundaries for this milestone
Free local discovery and deterministic matching. Each user owns their profile and preferences. Recruiter/employee discovery follows this milestone, followed by tracking automation. Background refresh requires a running host and is scheduled in a later slice. Freshness means checked at a stated time, not guaranteed continuously live.

## Progress
- Initial code audit completed.
- Provider documentation identified.
- First implementation slice completed: profile role/geography review, three Lever boards, on-demand dashboard search, skill evidence, ranking and per-source errors.
- 52 Python and 9 JavaScript checks passed.
- Live feed reads succeeded for Hevo Data (53 postings), Zeta (31) and CRED (14) on 2026-11-01. Counts change over time.
- Remaining: editable discovery preference controls, broader experience levels, Greenhouse adapter, wider employer coverage and cached requests. Current eligibility still targets early-career software roles. This slice is not the complete universal discovery release.
