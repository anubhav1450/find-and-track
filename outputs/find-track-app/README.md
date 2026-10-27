# Find&Track

A private, local job-search workspace. Python 3 and a modern browser are the only requirements. No npm install, hosted account or paid API key is required.

## Run

Double-click **Find&Track.app** on macOS. It starts a local background server if needed and opens **http://127.0.0.1:8765** in your browser. Open it again to reuse the running server; you do not need to ask the assistant to launch it. Keep the bundle alongside `launch.py`, `server.py`, `static/` and `data/`. You can drag an alias of the app to the Dock for easier access.

Alternatively double-click `start.command`, or run `python3 launch.py` from this directory. `python3 server.py` still runs the server in a foreground terminal. A Mac restart stops the local server; opening the launcher starts it again. This is not an installed login service. If the default port is occupied by another program, use `python3 launch.py --port 8766`.

Opening the app loads saved research, current application states and pending follow-ups. Recommended and Needs review buttons show the two research groups. **Refresh jobs** attempts the first public employer feed (Hevo Data on Lever), then prepares every saved job from the master resume. Other sources still require assistant research. Refresh is on demand, with no scheduled background discovery. After updating an already-running older server, stop it once with Ctrl+C in its terminal and reopen the launcher to load the new endpoint.

## Working features

- Add/edit jobs; search and filter the shortlist; open posting links directly.
- Track applications separately from contacts. One-tap status buttons record your confirmation without a required comment. After “I applied”, the relevant recruiters open immediately. Optional status corrections remain under “Change status”; opening a posting link alone never changes status.
- Save recruiter profiles, relevance, uncertainty, status and message drafts. Recording an acceptance creates one follow-up task per person.
- Review requirements against a pasted exact JD. Full/partial resume evidence, known-but-omitted skills and learning gaps remain distinct. Required requirements have weight 2, preferred weight 1. Full evidence earns 1, partial earns 0.5, others 0. A score appears only after the exact JD/list is confirmed and every requirement is reviewed. This is checklist coverage, not an ATS score or hiring probability.
- Store master resume text and capture a private resume snapshot with each job assessment. Existing snapshots remain unchanged when the master resume changes. No PDF edits occur automatically.
- Keep job notes, sourced activity and follow-up tasks; download resume text, jobs CSV and a full JSON backup.
- Import/merge research backups by stable record IDs. Merge preserves existing records; restore replaces the workspace. Previous revisions remain in database history.
- Open targeted public job, career-page and recruiter search links.
- Use the master resume as candidate evidence, with separately confirmed knowledge and eligibility preferences. Each job receives matched terms, missing terms, suggested emphasis and a downloadable text resume draft. Automatic edits emphasize supported skills in the profile paragraph; the master stays unchanged. Full JD scoring remains a separate reviewed checklist.
- Complete old application tasks after an Applied tap, queue recruiter research when contacts are missing, prepare a message when acceptance is recorded, and finish that task after Message sent. Existing reviewed drafts are preserved.

## Current integration boundaries

The initial records come from the previously reviewed Google Sheet. This application is now a separate local workspace; there is no automatic two-way Sheets sync. Gmail, public-web research and connected tools do not automatically become available to a local browser app. Most research remains assistant-driven. The new refresh integration uses the documented public [Lever postings API](https://github.com/lever/postings-api) for one employer. The app does not run a background Gmail monitor or automatically send applications/LinkedIn messages.

An assistant can pass a bounded, normalized email batch to `python3 workflow.py --mail /absolute/path/to/messages.json`. Unique, explicit, authenticated receipts and connection acceptances can advance tracked records. Ambiguous or unauthenticated matches need review; unrelated acceptances and job alerts are ignored. Email ingestion is a bridge, not Gmail OAuth or continuous sync. `python3 workflow.py --refresh` performs the same on-demand preparation/feed operation as the button. Feed failures are reported and preserve saved jobs; no deletion is inferred from missing postings.

To research a batch, export the JSON, provide it to your assistant along with this README, and ask for new source-backed records in the same schema. Import the result using **Merge new records**. To update an existing record, use its in-app editor. Import **Restore entire backup** only when you intend to replace the complete state with a reviewed backup. Import files must contain all standard schema arrays, even when empty.

An assistant with access to this workspace can load a research batch directly using `python3 research.py /absolute/path/to/batch.json`. The batch may contain jobs, companies, contacts, events and actions. The helper merges new records in a single transaction, deduplicates posting URLs and preserves existing application/contact states. Replaying the same batch adds no records. Reload the browser after an assistant update.

## Private data

A fresh clone uses `seed.example.json`, which contains no personal records. If a private `data/seed.json` exists, it seeds the initial personal workspace instead. `data/workspace.sqlite3` holds the current state and up to 50 earlier revisions. Both are private and excluded by `.gitignore`. Do not publish either, exported backups, or your private resume. No external scripts, fonts, analytics or remote runtime dependencies are loaded. The server binds to loopback only and rejects unexpected Host/Origin values; writes require a per-process token and an up-to-date revision.

For recovery, stop the app, copy `data/workspace.sqlite3`, and inspect the `history` table with SQLite. Export a chosen JSON payload and restore it through the UI. The seeded data is read once on first launch; editing the seed never overwrites an existing workspace.

## Validation

Run `python3 -m unittest discover -s tests -v` and `node --test tests/domain.test.cjs tests/render.test.cjs`. Tests use a temporary database, not your personal workspace. The default Python suite runs HTTP request parsing and handlers in memory without opening sockets; use `FIND_TRACK_HTTP_TEST=1 python3 -m unittest discover -s tests -v` for actual loopback HTTP tests. They exercise persistent writes, optimistic concurrency, malformed imports, unsafe URLs, request protection and backup history. JavaScript tests cover weighted scoring, job deduplication, repeat imports, acceptance tasks and reviewed keyword suggestions.

## Scope

Personal prototype v0.3. No guarantee of complete job-market coverage, recruiter response, employer legitimacy or current availability. Confirm vacancy-specific terms before applying. A public open-source release still needs a generic empty seed and a deliberate license decision; this private build is not published.
