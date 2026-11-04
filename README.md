# Find&Track

Find&Track is a free, local-first job tracker for people looking for early-career software roles. Import your resume, discover roles across supported sources, check why a job matches, and keep applications and recruiter follow-ups in one place.

I started it during my own job search in India. The project is in active development and open to contributions and ideas. [Suggest an idea or report a missed job](https://github.com/anubhav1450/find-and-track/issues/new).

![Find&Track showing a fictional candidate and sample opening](docs/assets/sample-workspace.png)

## Run your own workspace

With Git and Python 3 installed, run these commands on macOS or Linux:

```sh
git clone https://github.com/anubhav1450/find-and-track.git
cd find-and-track
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python outputs/find-track-app/launch.py
```

Open [the local dashboard](http://127.0.0.1:8765/), import your resume under **Resume & rules**, then select **Refresh jobs**. Local discovery requires internet access to read listings. You can run the tracker without a paid AI subscription or a cloud account. The [hosted workspace](https://find-and-track.vercel.app/) requires owner sign-in.

## What you can do

- **Discover roles.** Search remote software listings from Remotive and selected employer boards on Greenhouse and Lever. The current focus is India and early-career software jobs. Coverage varies by employer and day.
- **Check freshness.** “Posted today” uses the publication date supplied by the source. “Added today” uses the date a listing entered your tracker. A refresh can find zero newly published matches.
- **Prepare and track.** Review skill matches and gaps, open the original posting, apply yourself, and record the outcome. Keep relevant people and follow-up drafts alongside the job. Compensation and recruiter ownership may need confirmation.

## How it works

The browser dashboard calls a Python backend that stores local records in SQLite. Discovery reads public feeds and compares job descriptions with the saved profile. The optional hosted setup uses Vercel and Supabase. Automatic inbox monitoring and comprehensive job-board coverage are still open work.

[App guide](outputs/find-track-app/README.md) · [Discovery roadmap](docs/DISCOVERY_V02.md) · [Deployment](DEPLOYMENT.md)

## Contribute

Ideas, bug reports, better source coverage and improvements to job matching are welcome. A public link to a job we missed, plus the role and location you searched for, is particularly helpful. [Contribution guide](CONTRIBUTING.md) · [Open issues](https://github.com/anubhav1450/find-and-track/issues)

MIT licensed. The bundled Inter font has its own OFL license. [Project license](LICENSE) · [Font license](outputs/find-track-app/static/Inter-OFL.txt)
