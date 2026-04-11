# ClipPods – Contributor Guide

## Branch Ownership

| Branch | Owner | Files to Edit |
|--------|-------|---------------|
| `feat/ml-eng1-transcription` | ML Engineer 1 | `backend/services/transcription.py` |
| `feat/ml-eng2-highlight-clip` | ML Engineer 2 | `backend/services/highlight.py`, `backend/services/clip.py` |
| `feat/backend-pipeline` | Backend Engineer | `backend/main.py`, `backend/config.py`, `backend/models.py` |
| `main` | Team Lead (merge only) | Everything — via Pull Request |

> **Rule:** Never commit directly to `main`. All changes flow through a PR from your feature branch.

---

## First-Time Setup (every team member)

```bash
git clone https://github.com/Dhilshan-codebox/SaaS_Hackathon.git
cd SaaS_Hackathon

python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Mac/Linux

pip install -r requirements.txt
```

---

## Daily Workflow

### 1 – Switch to your branch
```bash
# ML Engineer 1
git checkout feat/ml-eng1-transcription

# ML Engineer 2
git checkout feat/ml-eng2-highlight-clip

# Backend Engineer
git checkout feat/backend-pipeline
```

### 2 – Pull latest changes from main before starting
```bash
git fetch origin
git merge origin/main        # keep your branch up-to-date
```

### 3 – Edit ONLY your assigned files (see table above)

### 4 – Commit your work
```bash
git add backend/services/transcription.py   # only your file(s)
git commit -m "feat(transcription): integrate Sarvam AI saaras:v3 response"
git push
```

### 5 – Open a Pull Request on GitHub
- Go to: https://github.com/Dhilshan-codebox/SaaS_Hackathon/pulls
- Click **New pull request**
- Base: `main`  ←  Compare: `your-feature-branch`
- Add a description of what you changed and tag the team lead for review

---

## Resolving Merge Conflicts

If `git merge origin/main` shows conflicts:

```bash
# Open the conflicting file, look for <<<<<<< markers, fix them
git add <conflicting-file>
git commit -m "fix: resolve merge conflict with main"
git push
```

---

## Running Locally

```bash
# From the project root (SaaS_Hackathon/)
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

- Landing page: http://localhost:8000/
- App dashboard: http://localhost:8000/app
- API docs:      http://localhost:8000/docs

---

## models.py is a shared contract ⚠️

`backend/models.py` is the **single source of truth** for all data shapes.
- Do NOT rename fields without coordinating with the full team
- Any change to `models.py` must be done in `feat/backend-pipeline` and approved via PR before others pull
