# AgentCost — Publishing Setup Checklist

Complete step-by-step guide to set up automated publishing to PyPI, npm, and GitHub Container Registry (GHCR).

---

## Accounts & Domain

| Service    | Account Email            | URL                                         |
| ---------- | ------------------------ | ------------------------------------------- |
| **GitHub** | `agentcost.in@gmail.com` | github.com/agentcostin                      |
| **PyPI**   | `agentcost.in@gmail.com` | pypi.org/project/agentcostin                |
| **npm**    | `agentcost.in@gmail.com` | npmjs.com/~agentcost-ai (org: @agentcostin) |
| **Domain** | GoDaddy (`agentcost.in`) | agentcost.in                                |

**Emails in codebase:**

- `open@agentcost.in` — public-facing (author, contact, security, conduct)
- `care@agentcost.in` — support (alerts, notifications, demo user)

---

## 0. GitHub Account & Repositories (Do This First)

### Step 1: Create GitHub account

- Go to https://github.com/signup
- Sign up with `agentcost.in@gmail.com`
- Username: `agentcostin`

### Step 2: Create two repositories on GitHub

Go to https://github.com/new and create each repo **before** pushing:

| Repo                           | Visibility  | Contents                                             |
| ------------------------------ | :---------: | ---------------------------------------------------- |
| `agentcostin/agentcost`        | **Public**  | Main codebase (from agentcost-phase7-complete.zip)   |
| `agentcostin/agentcost-keygen` | **Private** | Enterprise key generator (from agentcost-keygen.zip) |

**Important:** When creating, do NOT initialize with README, .gitignore, or license — the repos must be empty.

### Step 3: Push code

When prompted, enter username `agentcostin` and your Personal Access Token as password.

```bash
# Main repo (public)
cd agentcost
git init
git remote add origin https://github.com/agentcostin/agentcost.git
git add -A
git commit -m "release: v1.0.0"
git branch -m master main
git push --set-upstream origin main

# Keygen repo (private — separate folder)
cd ../agentcost-keygen
git init
git remote add origin https://github.com/agentcostin/agentcost-keygen.git
git add -A
git commit -m "initial: license key generator"
git branch -m master main
git push --set-upstream origin main
```

Once done, proceed to set up PyPI, npm, and the other services below.

---

**Yes, 100%.** Here's what's free:

| Service             | Free for Public Repos? | Limits                                            |
| ------------------- | :--------------------: | ------------------------------------------------- |
| **GitHub Actions**  |      ✅ Unlimited      | No minute limits for public repos                 |
| **PyPI**            |        ✅ Free         | No limits for open-source packages                |
| **npm**             |        ✅ Free         | Public packages are free, no limits               |
| **GHCR**            |        ✅ Free         | Public container images are free, unlimited pulls |
| **GitHub Pages**    |        ✅ Free         | For docs site (agentcost.in/docs)                 |
| **GitHub Releases** |        ✅ Free         | Auto-generated with each tag                      |

**Key requirement:** Your repository must be **public** (which it will be, since AgentCost is open-source). Private repos on free accounts get only 2,000 Actions minutes/month.

---

## 1. PyPI — Python Package (pip install agentcostin)

### One-Time Setup

**Step 1: Create PyPI account**

- Go to https://pypi.org/account/register/
- Sign up with `agentcost.in@gmail.com`
- Verify email and enable 2FA

**Step 2: Create an API token**

- Go to https://pypi.org/manage/account/#api-tokens
- Click "Add API token"
- Token name: `agentcostin-upload`
- Scope: "Entire account" (first time; you can scope to project later)
- Copy the token (starts with `pypi-`) — you won't see it again

**Step 3: Build and publish**

```bash
# Install build tools
pip install build twine

# Build the package
python3 -m build
ls dist/
# Should see: agentcostin-1.0.0.tar.gz and agentcostin-1.0.0-py3-none-any.whl

# Upload to PyPI
twine upload dist/* -u __token__
# When prompted for API token, paste your pypi-... token
```

**Step 4: Verify it works**

```bash
pip install agentcostin
python -c "from agentcost.sdk import trace; print('✅ agentcostin installed')"
agentcost info
```

Published at: https://pypi.org/project/agentcostin/

### Automated Publishing (GitHub Actions)

For future releases, you can set up Trusted Publishing (OIDC) so GitHub Actions publishes automatically on tag push:

- Go to https://pypi.org/manage/project/agentcostin/settings/publishing/
- Add a new publisher:
    - **Owner:** `agentcostin`
    - **Repository:** `agentcost`
    - **Workflow name:** `ci.yml`
    - **Environment name:** leave blank

Then future releases just need:

```bash
git tag v1.1.0
git push origin v1.1.0
# CI builds and publishes automatically
```

---

## 2. npm — TypeScript SDK (@agentcostin/sdk)

### One-Time Setup

**Step 1: Create npm account**

- Go to https://www.npmjs.com/signup
- Sign up with `agentcost.in@gmail.com` and verify email
- Username: `agentcost-ai`

**Step 2: Enable 2FA (required for publishing)**

- Go to https://www.npmjs.com/settings/agentcost-ai/security
- Enable 2FA using an authenticator app

**Step 3: Create the npm org/scope**

- Go to https://www.npmjs.com/org/create
- Create org named `agentcostin`
- This reserves the `@agentcostin` scope

**Step 4: Build and publish**

```bash
cd sdks/typescript
npm install
npm run build
npm login        # login as agentcost-ai
npm publish --access public
```

Published at: https://www.npmjs.com/package/@agentcostin/sdk

### Automated Publishing (GitHub Actions)

For future releases, add an npm token to GitHub:

- Go to https://www.npmjs.com/settings/agentcost-ai/tokens
- Generate a **Granular Access Token** with publish permissions
- Add to GitHub: repo → Settings → Secrets and variables → Actions → `NPM_TOKEN`

Then CI publishes automatically on tag push.

### After Publishing

```bash
npm install @agentcostin/sdk
node -e "const { AgentCost } = require('@agentcostin/sdk'); console.log('✅ @agentcostin/sdk installed')"
```

---

## 3. GHCR — Docker Image (ghcr.io/agentcostin/agentcost)

### One-Time Setup

**No setup needed!** GHCR uses the built-in `GITHUB_TOKEN` that GitHub Actions provides automatically. No secrets to configure.

After the first push, you just need to make the package public:

**Step 1: Push a tag** (this triggers the Docker workflow)

```bash
git tag v1.0.0
git push origin v1.0.0
```

**Step 2: Make the package public**

- Go to https://github.com/orgs/agentcostin/packages (or your user packages page)
- Click on the `agentcostin` package
- Click "Package settings"
- Scroll to "Danger Zone" → "Change package visibility"
- Set to **Public**

### How Publishing Triggers

The `.github/workflows/docker.yml` runs on tag push:

1. Builds community image → `ghcr.io/agentcostin/agentcost:latest`
2. Builds enterprise image → `ghcr.io/agentcostin/agentcost:enterprise`
3. Tags with version number too

### After Publishing

```bash
docker pull ghcr.io/agentcostin/agentcost:latest
docker run -p 8100:8100 ghcr.io/agentcostin/agentcost:latest
# → http://localhost:8100
```

---

## 4. GitHub Pages — Documentation Site

### One-Time Setup

**Step 1: Enable GitHub Pages**

- Go to repo → Settings → Pages
- Source: **GitHub Actions**
- Click "Save"

### How Publishing Triggers

The `.github/workflows/docs.yml` runs on every push to `main` that changes `docs/` or `mkdocs.yml`. It builds MkDocs and deploys to GitHub Pages.

### Custom Domain (Optional)

To use `agentcost.in/docs`:

1. In repo → Settings → Pages → Custom domain → enter `agentcost.in/docs`
2. Add DNS records in **GoDaddy** (https://dcc.godaddy.com/manage/agentcost.in/dns):

    | Type  | Name   | Value                   | TTL |
    | ----- | ------ | ----------------------- | --- |
    | CNAME | `docs` | `agentcostin.github.io` | 600 |
    | A     | `@`    | `185.199.108.153`       | 600 |
    | A     | `@`    | `185.199.109.153`       | 600 |
    | A     | `@`    | `185.199.110.153`       | 600 |
    | A     | `@`    | `185.199.111.153`       | 600 |
    | CNAME | `www`  | `agentcostin.github.io` | 600 |

    **GoDaddy steps:** DNS → DNS Records → Add New Record → select type, fill in Name and Value

3. Enable "Enforce HTTPS" in GitHub Pages settings (wait 5–10 min for DNS propagation)

This gives you:

- `agentcost.in` → landing page
- `agentcost.in/docs` → MkDocs documentation site
- `www.agentcost.in` → redirects to main site

---

## 5. License Key System (Enterprise)

AgentCost uses a license key system to gate enterprise features. Trial keys are self-service; enterprise keys are generated from a **separate private repo** (`agentcost-keygen`).

### Architecture

| Repo                           | Visibility  | Contains                                                   |
| ------------------------------ | :---------: | ---------------------------------------------------------- |
| `agentcostin/agentcost`        | **Public**  | Trial key generation, key validation, activate/deactivate  |
| `agentcostin/agentcost-keygen` | **Private** | Enterprise key generation, customer ledger, signing secret |

### One-Time Setup

**Step 1: Create a signing secret**

```bash
cd agentcost-keygen
python keygen.py secret
# → Generates a 64-char hex secret
```

**Step 2: Set the secret in BOTH places**

The secret must match between the keygen tool and the AgentCost server.

- **Keygen repo (local):** `export AGENTCOST_LICENSE_SECRET='<secret>'`
- **AgentCost server (production):** Add `AGENTCOST_LICENSE_SECRET` as:
    - GitHub repo secret (for Docker builds): Settings → Secrets → `AGENTCOST_LICENSE_SECRET`
    - Docker Compose env var: in `docker-compose.yml` under `environment:`
    - Direct server: `export AGENTCOST_LICENSE_SECRET='<secret>'`

**Step 3: Create the private keygen repo**

```bash
cd agentcost-keygen
git init
git remote add origin https://github.com/agentcostin/agentcost-keygen.git
git add -A
git commit -m "initial: license key generator"
git branch -m master main
git push --set-upstream origin main
```

Make sure the repo is **Private** on GitHub.

### Generating Keys for Customers

```bash
# Enterprise key (1 year, unlimited users)
python keygen.py generate --to "Acme Corp"

# Enterprise key (50 users, 1 year)
python keygen.py generate --to "Acme Corp" --users 50

# Trial key (30 days)
python keygen.py generate --to "Prospect Inc" --tier trial --days 30
```

All keys are auto-logged to `keys-ledger.csv`.

### Customer Activation

Send the key to the customer. They activate with:

```bash
agentcost license activate 'AC-xxxx-...'
agentcost license status   # verify
agentcost info             # shows Enterprise edition
```

---

## Complete Publishing Checklist

### Before First Release

- [ ] GitHub account created (agentcost.in@gmail.com)
- [ ] Public repo `agentcostin/agentcost` created and code pushed
- [ ] Private repo `agentcostin/agentcost-keygen` created and code pushed
- [ ] PyPI account created, API token generated
- [ ] Trusted Publisher configured on PyPI (pointing to `ci.yml`)
- [ ] npm account created
- [ ] npm access token generated and added as `NPM_TOKEN` secret in GitHub
- [ ] npm account created (`agentcost-ai`), 2FA enabled, `@agentcostin` org created
- [ ] GitHub Pages enabled (Source: GitHub Actions)
- [ ] `AGENTCOST_LICENSE_SECRET` generated and set on production server
- [ ] Private `agentcost-keygen` repo created on GitHub
- [ ] `pyproject.toml` version is `1.0.0`
- [ ] `sdks/typescript/package.json` version is `1.0.0`
- [ ] `CHANGELOG.md` updated
- [ ] All tests pass: `python scripts/verify_release.py --full`

### Release Day

```bash
# 1. Final verification
make verify                    # 18/18 ✅

# 2. Commit everything
git add -A
git commit -m "release: v1.0.0"
git push origin main

# 3. Tag and push (this triggers all CI publishing)
git tag v1.0.0
git push origin v1.0.0

# 4. Watch CI at https://github.com/agentcostin/agentcost/actions
#    - lint ✅
#    - test (3.10, 3.11, 3.12, 3.13) ✅
#    - community-mode ✅
#    - build ✅
#    - publish-pypi ✅
#    - publish-npm ✅
#    - docker build+push ✅
#    - release (GitHub Release with auto-changelog) ✅

# 5. Make GHCR package public (first time only)
#    → GitHub repo → Packages → agentcostin → Settings → Change visibility → Public

# 6. Verify all endpoints
pip install agentcostin && agentcost info
npm install @agentcostin/sdk
docker pull ghcr.io/agentcostin/agentcost:latest
```

### Post-Release

- [ ] Verify `pip install agentcostin` works on a clean machine
- [ ] Verify `npm install @agentcostin/sdk` works
- [ ] Verify `docker pull ghcr.io/agentcostin/agentcost:latest` works
- [ ] GitHub Release page has auto-generated changelog
- [ ] Docs site is live (GitHub Pages)
- [ ] Post Show HN (`community/show-hn-draft.md`)
- [ ] Post Twitter thread (`community/twitter-launch-thread.md`)
- [ ] Post LinkedIn (`community/linkedin-launch-post.md`)
- [ ] Publish blog post (`community/launch-blog-post.md`)

---

## Cost Summary

| Service                                       | Monthly Cost |
| --------------------------------------------- | :----------: |
| GitHub (public repo + Actions + Pages + GHCR) |    **$0**    |
| PyPI                                          |    **$0**    |
| npm (public packages)                         |    **$0**    |
| **Total**                                     |    **$0**    |

Everything is completely free for a public open-source project on a free GitHub account.
