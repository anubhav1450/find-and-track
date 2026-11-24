# Resume-driven discovery v0.2

## Product decision: search by role

A user imports a resume and taps Find jobs. Derive target titles from saved preferences and skills, search across employers, inspect responsibilities and eligibility, then rank by resume evidence. A company list is optional supplemental coverage. Keep an unverified lead in Needs review until the original employer confirms the opening. Preserve provider attribution and application progress across searches.

First slice: search the Remotive software catalog locally using derived role terms, with a six-hour process cache. Remote coverage only. Supplemental Lever boards still provide direct postings. Next slice: broader India onsite/hybrid sources, JD-based handling of ambiguous titles, employer verification and screening corrections. Evaluate live yield and manually review accepted and rejected jobs before calling the milestone complete.

## Outcome
Import a resume, confirm extracted skills and search preferences, press Find jobs, and receive current employer postings ranked against that profile. Each result links to its source and explains matches, gaps and uncertainty.

## Current implementation audit (2026-11-24)
The app reads the Remotive software catalog and fourteen employer boards across Lever, Greenhouse and Ashby, plus connected role-based web search. Coverage is a bounded set of sources. Posting dates remain distinct from first-seen and checked times. The dashboard opens on Current leads, shows the latest refresh summary, and exposes rejection reasons and unavailable sources.

Add job accepts a Greenhouse, Lever or Ashby posting URL, fetches the original public ATS record, previews its description and profile comparison, and saves only after review. Unsupported sources have a manual-entry fallback. AccioJob is linked as an external curated discovery source. Its published terms restrict copying and mirroring, so automatic collection needs permission or a suitable licensed feed before implementation. Original supported employer links discovered there can be imported.

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
- Remaining: editable discovery preference controls, broader experience levels, wider employer coverage and broader request caching. Current eligibility still targets early-career software roles. This slice is not the complete universal discovery release.

## Reliability update — 2026-11-24
- Job-link preview works through local and cloud routes with session checks, fixed ATS endpoints, response limits and redirect rejection.
- URL deduplication ignores tracking parameters while retaining requisition identifiers.
- Screening records rejection reasons and skips malformed feed records. Explicit required experience takes precedence over a role-family review.
- Imported source text is visible in job details. Resume saving triggers fresh preparation and discovery.
- Resume drafts avoid assuming internship experience; generic “go” text no longer implies the Go language.
- Limitations remain: bounded provider coverage, on-demand refresh, employer eligibility review, manual recruiter discovery, and no background Gmail monitor.

## Unified discovery and tracking — 2026-11-24

### What live research found
- A small static employer list cannot discover new startups. Add role-first search across job sources, then resolve supported results through the original employer feed.
- Search indexes can retain removed openings. Successful ATS retrieval establishes current listing presence, while indexed-only leads retain availability uncertainty.
- Employer names can collide with generic industries. Drivetrain searches initially returned automotive profiles. Match explicit employer relationships and use the identified company domain to narrow queries.
- Seniority appears in many formats, including “3–6 years in frontend engineering” and “Software Development Engineer 3”. Test those against fresher screening.
- Small companies can have fewer than ten HR staff. Target ten relevant recruiter, HR and engineering contacts, show the split and shortfall, and keep activity unconfirmed without dated evidence.

### Implemented flow
1. Import a supported posting (Greenhouse, Lever, Ashby), or resolve another indexed job link through connected search. Review employer and role before saving.
2. Saving a new job starts company/contact research. The research panel retains identity sources, complaint-related results, hiring posts, timestamps, partial failures and up to 20 deduplicated contact leads.
3. Connection requests, acceptance, outreach and applications use the existing explicit status actions. Research does not send messages or submit applications.
4. Refresh jobs reads employer feeds and, when search is connected, runs role-first web queries. Indexed-only results with identifiable employer/title enter review with a visible source label. Links without adequate metadata remain in Discover.
5. Current leads hides known absent postings, excluded matches and publication dates older than 30 days. All retains history. Undated employer listings show their checked date and unknown publication date.

### Search setup and costs
Tavily's free Researcher account currently includes 1,000 credits/month with no card. Use basic search, keep pay-as-you-go disabled, and save the key in Discover. A company research run requests at most 12 basic searches, cached for six hours. The app reserves requests atomically and caps them at 900 per key per UTC calendar month in its local cache. Other applications using the key consume the same provider allowance. The local cap is per cache installation; hosted ephemeral instances do not share a global meter.

The key is server-only, saved with owner-only file permissions, excluded from Git and workspace exports. Hosted deployments use TAVILY_API_KEY; hosted key entry is disabled. API cache defaults to a temporary directory on Vercel. Workspace records remain the source of saved user research and tracking.

### Honest verification boundaries
Company evidence is not a fraud clearance. A complaint search hit is a lead requiring identity and source review. Contact affiliation is indexed evidence, and current activity remains unconfirmed. Ashby dates describe last publication and may represent reposting. Search date is not job publication date. Gmail background monitoring remains outside this release.

### References checked
- https://developers.ashbyhq.com/docs/public-job-posting-api
- https://docs.tavily.com/documentation/api-reference/endpoint/search
- https://help.tavily.com/articles/8298987937-billing-credits-usage-limits
- https://www.ycombinator.com/jobs/role/all/india
- https://acciojob.com/terms-and-conditions

### Verification for this update
73 Python tests and 10 JavaScript tests passed. A real Chromium session completed role search, saved company/contact research, and reopened an existing posting on duplicate import with zero runtime errors. Live startup feeds and the saved Tavily key were exercised. The final web search returned five indexed-only leads; none of those five was a verified ATS match. They retain review labels.
