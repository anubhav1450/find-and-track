# Contributing to Find&Track

[Open an issue](https://github.com/anubhav1450/find-and-track/issues/new) for an idea, a missed vacancy or a confusing part of the workflow. For a matching problem, include the public posting, the role and location searched, the expected result and what the app showed. A fictional resume snippet is enough. Keep personal resumes, recruiter correspondence and credentials private.

For a code change, fork the repo, create a branch, and follow the setup in the README. Keep the pull request focused. Explain what changed for the job seeker and how you verified it. For new job sources, link the provider documentation, describe access and attribution requirements, and explain how timestamps and unavailable feeds are handled.

Run the backend and dashboard checks from the repository root (Node.js is needed for the dashboard checks):

```sh
.venv/bin/python -m unittest discover -s outputs/find-track-app/tests
node --test outputs/find-track-app/tests/*.test.cjs
```
