# Private cloud deployment

The local app and its SQLite data remain intact. The cloud entrypoint uses the existing UI with a separate storage and authentication adapter. Hosting does not add background Gmail monitoring.

## Services

- Vercel project: `find-and-track`, connected to the private repository. Keep deployment protection enabled.
- Supabase: dedicated Free `find-and-track` project in the personal Find and Track organization, in Mumbai. Its database schema is applied; the application does not need the database password.
- Supabase email sign-in links with PKCE authenticate the owner. New email sessions are checked server-side with the provider before any workspace access. Cookies are Secure, HttpOnly, SameSite=Lax and host-scoped; writes also require matching Origin and CSRF token.

## Complete configuration

1. Create the dedicated Supabase project. Use a generated strong database password and keep it in your password manager. The app never needs this password or a service-role key.
2. Run `supabase/001_workspace.sql` in its SQL editor. It creates ownership-protected workspace/history tables, row-level security and an atomic revision-aware save function. The SQL contains no personal records.
3. Keep the default email templates. Configure the Site URL as the stable HTTPS app origin and allow its exact `/auth/callback` URL. Sign-in uses a browser-bound PKCE verifier stored in a Secure, HttpOnly cookie. The default sender restricts delivery to organization members and applies rate limits. Use the configured workspace-owner email; changing delivery or membership requires separate setup.
4. Set four Vercel server variables for Production: `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `FINDTRACK_OWNER_EMAIL`, `APP_ORIGIN`. Use the actual stable HTTPS app origin, without a trailing slash. The publishable/anon key is sufficient. Keep private keys out of Git and logs. Grant the owner email only after confirming which email receives the sign-in code.
5. Redeploy the reviewed commit. Without configuration, private APIs fail closed and the homepage reports setup pending. No fallback to temporary local storage is allowed in cloud mode.
6. Sign in, export a local JSON backup, and use **Restore entire backup** in the empty cloud app. This transfers personal data to the selected Supabase project through the authenticated API, not into source control. Preserve the local database and backup.

## Acceptance checks before calling the app ready

- The real owner can receive and verify an email sign-in link, read their jobs and sign out.
- An unsigned request to `/api/state` cannot read the workspace; a different verified account is denied by the application and cannot read another owner's rows through RLS.
- Saving a status, reloading on another device and redeploying retains the saved status.
- Two stale tabs produce a conflict without overwriting newer data.
- The imported resume, job count, contacts and application states match the local backup.
- The actual SQL migration and provider round trip are exercised against the dedicated project. Mock HTTP tests alone do not confirm this.

Free service limits and inactive-project pausing apply. Do not disable protection or publish personal workspace data to work around setup problems.

## Verified deployment

Production: https://find-and-track.vercel.app. Email-link sign-in and the authenticated database round trip were verified. The local workspace was imported through the authenticated restore flow. A live Hevo refresh added one employer-posted internship, leaving 20 jobs and 9 contacts. Reload preserved those records. Unauthenticated app access and anonymous direct database access returned 401. Local and cloud workspaces are separate copies; no automatic two-way sync is configured.
