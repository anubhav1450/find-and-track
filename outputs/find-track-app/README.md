# App guide

Start with the [repository setup guide](../../README.md). This is a standalone local-first workspace; Alan and connected assistant tools are optional legacy integrations, not runtime requirements.

## Daily use

Import and review your resume in Resume & rules. Set your role/location preferences before refreshing. Employer feeds work without a key; Discover → Connect search enables optional role-based web search and company research using your own Tavily account.

The shortlist defaults to Current leads. Posted today uses source publication dates; Added today uses the first discovery date. All retains history, including older or unavailable jobs. Zero additions refers only to the sources checked. Open the original posting to confirm availability and terms.

Add job → Import posting accepts supported ATS links and indexed posting links. Review before saving. Company research collects linked evidence and recruiter/employee leads; unsupported or ambiguous information remains unconfirmed. Recording I applied opens the people workflow. Opening a link alone does not mark an application submitted. Outreach and job applications stay under your control.

## Resume and tracking

Keep your master resume unchanged and review job-specific suggestions. Known-but-omitted skills differ from demonstrated experience. Checklist coverage is shown only after the JD and requirements are reviewed; it is not a hiring probability. Downloadable drafts are text, not automatically redesigned PDFs.

Track applications separately from contacts. Acceptance creates a follow-up task; Message sent completes it. Existing reviewed drafts are preserved. Export jobs CSV or a full JSON backup. Merge adds new records; Restore replaces the workspace, so export a backup first.

## Local storage and recovery

`data/workspace.sqlite3` contains personal records and up to 50 previous revisions. `data/search-key.json` and `data/search-cache.sqlite3` hold private search configuration/cache. All are excluded from Git. A fresh installation uses the empty `seed.example.json`; an existing private seed is only used at first database creation.

To back up, use the UI JSON export. For database recovery, stop the app before copying the SQLite database. Launch again with the same directory to retain records. Do not publish exports or the data directory.

The launcher starts a background loopback server. Restart it after updating code. For explicit foreground control, run `.venv/bin/python outputs/find-track-app/server.py` from the repository root and stop with Ctrl+C. No scheduled background discovery or Gmail OAuth is included. Email batch ingestion is a developer bridge, not continuous Gmail sync.

## Checks

From the repository root:

```sh
.venv/bin/python -m unittest discover -s outputs/find-track-app/tests
node --test outputs/find-track-app/tests/*.test.cjs
```

Tests use temporary data and mocked external providers. `FIND_TRACK_HTTP_TEST=1` enables additional loopback HTTP checks. See [contribution guidelines](../../CONTRIBUTING.md).
