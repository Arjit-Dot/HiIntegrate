# 1. Overview: the problem, our solution, and where AI fits

[Back to the README index](../../README.md) · Next: [2. Architecture](2-architecture.md)

## 1.1 The problem

A security team uses many tools: GitHub, Okta, Jira, vulnerability feeds and more. Each has its own API, its own login method,
its own paging, and its own names for the same things (a person is `login`, `profile.email` or `mail`). To answer a simple
question such as "who has an account anywhere, and is anything failing?", someone writes a one-off script per tool. Those scripts
break silently when a field is renamed, keep tokens in the wrong places, and nobody sees which ones are healthy.

## 1.2 Our solution

HiIntegrate is a **config-driven integration platform**. Adding a tool means writing a **config**, not code:

1. One generic **engine** reads the config, calls the service (with paging, retries and rate limits), and maps each response
   into one of three **common schemas**: `user`, `device` or `alert`.
2. Records that fail the rules are **quarantined**, never lost and never silently dropped. The run carries on.
3. Every pull is a recorded **run**. **Health** is computed from real runs, and repeated failures send an **email alert**.
4. A **dashboard** lets a person add, test, run, inspect and fix integrations without touching a file.
5. Secrets are stored **encrypted**, by name, and each one is **pinned to the host** it may be sent to.

The result: people from different services appear once in one **People** view, alerts from different feeds sit in one table,
and a broken tool shows up as a red health badge instead of a missing report.

## 1.3 Where AI falls in (and where it does not)

AI is an **optional helper**. Everything works with AI switched off (no `LLM_API_KEY`), and AI never decides anything alone.

| Feature | What the AI does | What keeps it safe |
|---|---|---|
| **Draft a config** (Add integration, AI mode) | Reads a service name, a documentation link, or an uploaded document and writes a draft config | The draft goes through the same validator, is **tested on the real service**, and nothing is saved until a person presses Save |
| **Fix with AI** (Quarantine) | Reads the rejected originals and proposes a config change | The platform **re-maps the stored records** with the proposal and shows "rescues N of M" before anything is applied |
| **Suggest mapping** (Add integration) | Suggests where each field comes from, given a sample reply | Every suggested path is checked against the sample ("matched 1 of 1") |
| **Summarize** (Results) | Words a summary of the table | The **database computes the numbers**; the model only words them. Names and emails are masked before anything reaches the model |

AI is **not** in the data path. The engine, the mapping, quarantine, health, alerts and storage are plain code and run
without a model. The AI routes live only in `backend/app/api/ai.py` and `backend/app/ai/`, so they can be removed or switched off.
The model is Google Gemini (see [3. Setup](3-setup.md#35-the-ai-key)).

## 1.4 Tech stack

| Layer | Technology |
|---|---|
| Backend API | Python 3.12, FastAPI, Uvicorn, Pydantic |
| Scheduler worker | APScheduler, in its own process |
| HTTP and mapping | httpx, JMESPath, PyYAML |
| Storage | SQLAlchemy 2; PostgreSQL 16 (Docker Compose), SQLite for tests and quick local runs |
| Secrets | `cryptography` (Fernet encryption), host pinning |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS, Monaco editor |
| Serving | nginx (static app and `/api` proxy), Docker Compose |
| AI (optional) | Google Gemini through `LLM_API_KEY` |
| Checks | pytest, ruff, a Node reference checker for the contract, GitHub Actions CI, gitleaks, Trivy |
