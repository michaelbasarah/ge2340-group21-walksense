# Owner upload and team access

Suggested name: **ge2340-group21-walksense**. Visibility: **private** because this contains sensor location/Wi-Fi identifiers and team work. This staged directory is a standalone local Git repository; no course folder has been turned into a repository.

Run from a normal terminal with working GitHub connectivity and authenticated `gh`. First review the committed contents and checks. Replace `OWNER` with your actual GitHub user or organization:

```sh
cd /home/basarah/personal/ge2340-team
git status --short
git log -1 --oneline
git remote -v
gh auth status
python3 scripts/validate_team.py
```

If any existing remote is listed, stop and verify it belongs to this exact intended repository before pushing. For a new repository only, after confirming the intended owner/name does not already exist:

```sh
gh repo create OWNER/ge2340-group21-walksense --private --source=. --remote=origin --push
```

`gh repo create` fails if that repository already exists; do not respond by force-pushing or overwriting an existing repository. If creation succeeds but push fails, inspect `git remote -v` and the new GitHub repository; retry `git push -u origin main` only after confirming the remote owner/name. No force push is needed.

On GitHub, open repository Settings → Collaborators and teams / Manage access. Invite each teammate's verified GitHub username with **write** access so they can upload label CSVs or use branches and pull requests. They must accept invitations. Organization policy may require an owner to manage access. Share the repository URL and direct them to `labeling/README.md`; raw HTML must be downloaded to run locally.

No teammate usernames or invitations have been guessed. Preparing or committing this workspace did not create a remote, publish a site, upload data or invite people. Keep the raw private chat and original identity/signature submission documents outside Git.
