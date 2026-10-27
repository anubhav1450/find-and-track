# Find&Track

A local workspace for finding relevant software jobs, preparing truthful resume drafts, tracking applications and organizing recruiter follow-ups.

## Use with Alan

The [Alan companion](ALAN_COMPANION.md) packages this workflow as a [skill](skills/find-track/SKILL.md) and local command-line bridge. Alan supplies research and reasoning; the bridge previews and saves approved jobs with duplicate and stale-profile checks. A fictional sample workspace is isolated from personal records.

```sh
python3 tools/findtrack.py demo
python3 tools/findtrack.py serve
```

Open http://127.0.0.1:8766, then follow the companion guide in an Alan local session. This does not expose the private hosted workspace or add an MCP server.

## Start

Python 3 and a modern browser are required. On macOS, open `outputs/find-track-app/Find&Track.app` or `outputs/find-track-app/start.command`. Alternatively:

```sh
python3 outputs/find-track-app/launch.py
```

The app opens at http://127.0.0.1:8765. A fresh clone starts with an empty example workspace. Add your profile and resume under **Resume & rules**, then add or import jobs. Existing local data is preserved.

## Workflow

Review jobs and resume gaps → apply manually → tap **I applied** → review recruiter profiles → connect manually → record acceptance → review a prepared message → send manually.

Resume drafts use stored evidence and confirmed knowledge. Complete JD coverage requires a reviewed checklist. Applications and LinkedIn outreach remain manual. Gmail matching accepts an imported email batch; independent Gmail monitoring is not connected. On-demand discovery currently implements one public employer feed, with wider research handled separately.

## Development

```sh
python3 -m unittest discover -s outputs/find-track-app/tests -v
node --test outputs/find-track-app/tests/domain.test.cjs outputs/find-track-app/tests/render.test.cjs
```

See [the application guide](outputs/find-track-app/README.md) for storage, privacy, integration boundaries and recovery details. Local resumes, inbox batches, job history, screenshots and research outputs are excluded from version control. This repository is a private prototype; no public license has been selected.
