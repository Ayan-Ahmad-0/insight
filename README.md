# Insight: Multi-Tenant Data & AI Platform

A multi-tenant backend for a SaaS client with ~40 business customers. It ingests feature and subscription events, produces daily morning numbers, answers plain-English questions about a customer's own usage with an AI analyst, and guarantees that no customer can ever see another customer's data. That guarantee is tested, not just claimed.

[![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Supabase](https://img.shields.io/badge/Supabase-3FCF8E?style=flat&logo=supabase&logoColor=white)](https://supabase.com/)
[![dbt](https://img.shields.io/badge/dbt-FF694B?style=flat&logo=dbt&logoColor=white)](https://www.getdbt.com/)
[![Gemini](https://img.shields.io/badge/Gemini-8E75B2?style=flat&logo=googlegemini&logoColor=white)](https://ai.google.dev/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white)](https://www.docker.com/)
[![Render](https://img.shields.io/badge/Render-46E3B7?style=flat&logo=render&logoColor=white)](https://render.com/)
[![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=flat&logo=githubactions&logoColor=white)](https://github.com/features/actions)
[![HTML5](https://img.shields.io/badge/HTML5-E34F26?style=flat&logo=html5&logoColor=white)](https://developer.mozilla.org/en-US/docs/Web/HTML)
[![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=flat&logo=javascript&logoColor=black)](https://developer.mozilla.org/en-US/docs/Web/JavaScript)

**Live demo:** [Web app](https://insight-1-g4j1.onrender.com) · [API](https://insight-sxrc.onrender.com)

A popup on the sign-in screen fills in a test account that belongs to a seeded demo organisation with fake data.

---
A popup on the sign-in screen fills in a test account that belongs to a seeded demo organisation with fake data.

## 📋 Overview

Insight is the capstone of a four-week build. It combines a data pipeline, a grounded AI assistant, and a deployed service into one production-style platform. It:

1. **Stores** user feature events and subscription events for ~40 customer organisations, each with several users
2. **Isolates tenants** with Postgres Row Level Security, backed by an automated isolation test suite that runs in CI
3. **Transforms** raw events into daily marts with dbt and produces a daily "morning numbers" digest
4. **Answers questions** through an AI analyst (Gemini) that has no SQL access and calls five fixed tools, each running under the caller's own RLS-scoped token
5. **Controls AI spend** with a cost ledger (`ai.calls`), a per-org daily budget, and per-org and global kill switches
6. **Serves** a clean FastAPI contract for a future front-end developer, plus a plain web dashboard as the client
7. **Deletes completely** when a customer leaves: `delete_org` removes all of an org's data and issues a receipt
8. **Runs like production**: scheduled jobs on GitHub Actions, an ops check, and a runbook from an unscheduled incident drill

---

## 🏗️ Architecture

**Events** → **Supabase Postgres (RLS)** → **dbt marts + daily digest** → **FastAPI (Render)** → **Web dashboard + AI analyst (Gemini)**

| Layer | Purpose | Tech |
| --- | --- | --- |
| **Ingest** | Feature + subscription events per organisation | Python, Postgres |
| **Storage & auth** | Multi-tenant schema, RLS policies, users and orgs | Supabase |
| **Transform** | Daily marts and morning digest | dbt |
| **Orchestration** | Scheduled pipeline runs and ops checks | GitHub Actions (cron) |
| **API** | Versioned contract for the dashboard and future front end | FastAPI, Docker, Render |
| **AI analyst** | Plain-English questions over a tenant's own data | Gemini, five fixed tools |
| **Client** | Dashboard served as a static site | HTML, JavaScript, Render Static Site |

### Architecture Diagram

<!-- TODO: add image -->
![Architecture Diagram](images/architecture_diagram.png)

### Tech Stack

- **Database & auth:** Supabase (managed Postgres), with RLS so every query is scoped to the caller's organisation
- **Pipeline:** Python ingestion plus dbt models for daily marts; digest generated after each run
- **Orchestration:** GitHub Actions cron (hosted and free), chosen over Airflow to keep the operational footprint small
- **API:** FastAPI in a Docker web service on Render
- **Web client:** Single-page dashboard (`web/index.html`) deployed as a Render Static Site
- **AI analyst:** Gemini with five fixed tools, a cost ledger table (`ai.calls`), a per-org daily budget, and per-org and global kill switches
- **CI:** Isolation test suite running against a throwaway Postgres on every PR

---

## 📊 Dashboard

<!-- TODO: add screenshots -->
![Dashboard](images/dashboard_1.png)
![Dashboard](images/dashboard_2.png)
![Dashboard](images/dashboard_3.png)


---

## 🔒 Tenant Isolation

The core requirement: **no customer can ever see another customer's data.**

- **Row Level Security** on every tenant-scoped table
- **Isolation tests** that run as one tenant and try to read or write another's rows, including tests on the AI cost ledger (`ai.calls`)
- **CI gate:** the suite runs on a throwaway Postgres for every pull request, so a bad policy can't merge
- **AI analyst scoping:** every tool call runs under the caller's token, and the eval set includes attack prompts aimed at cross-tenant leaks

<!-- TODO: add image of isolation test output / CI run -->
![Isolation Tests](images/isolation_tests.png)

---

## 🤖 AI Analyst

Customers ask plain-English questions about their own usage. The model has no SQL
access and never sees an org id: it calls five fixed tools (daily usage, feature
usage, MRR, digest, definitions), each running through Postgres RLS under the
caller's token. Every call is logged to `ai.calls` (tokens, cost, latency, tool
trace). There is a per-org kill switch, a per-org daily budget and a global switch.

<!-- TODO: add image -->
![AI Analyst](images/ai_analyst.png)

| Control | What it does |
| --- | --- |
| **Fixed tools only** | Five tools, no SQL access, no org id visible to the model |
| **RLS under caller's token** | Every tool call is scoped to the asking customer |
| **Cost ledger** | Every call logged to `ai.calls` (tokens, cost, latency, tool trace) |
| **Per-org daily budget** | Stops calls once an org reaches its limit |
| **Kill switches** | Per-org and global, no redeploy needed |

---

## ✅ Evaluation

37 questions: metrics checked against raw-table SQL, cited definitions,
canceled-org edge cases, out-of-scope, and 11 attack prompts.

- First run 26/30. The eval caught three real bugs: the model guessed dates
  (fixed by passing today's date), added numbers wrongly (fixed by precomputing
  totals in the tools), and skipped a citation.
- After fixes: 37/37, including 7 questions added after tuning. 0 cross-tenant
  leaks, 0 false refusals.
- Cost about $0.0004 per question; median latency 5.9 s (p95 8.9 s).

| Metric | Result |
| --- | --- |
| Questions passed | 37 / 37 |
| Cross-tenant leaks | 0 |
| False refusals | 0 |
| Average cost per question | ~$0.0004 |
| Median / p95 latency | 5.9 s / 8.9 s |

<!-- TODO: add image -->
![Evaluation Report](images/eval_report.png)

**Limits:** the eval set is small and uses two test orgs, answers can vary
between runs, and the budget check can overshoot by one question.

---

## 🗑️ Offboarding & Onboarding

- **Delete an organisation:** `delete_org` removes the org and all its data, rebuilds the marts without it, and prints a **receipt** as proof
- **Onboard an organisation:** the owner creates the org and first user with a local onboarding script. The customer then self-serves by uploading CSV data on the web page. There is no public self-signup.

---

## 🛡️ Operations

- **Scheduled runs:** pipeline and digest via GitHub Actions cron
- **Ops check:** `ops_check.py` runs on a schedule, and a failing step surfaces problems in GitHub Actions
- **Incident drill:** an unscheduled incident was handled during a production-style run, with a runbook written afterwards (see `docs/runbook.md`)

<!-- TODO: add image of GitHub Actions runs -->
![Operations](images/operations.png)

---

## 📁 Repository Structure

<!-- TODO: adjust to match the actual repo -->
```
insight/
├── README.md
├── requirements.txt
├── .env.example
├── Dockerfile
│
├── api/                    # FastAPI app (routes, auth, analyst endpoint)
├── web/
│   └── index.html          # Dashboard client
├── pipeline/               # Ingestion + digest jobs
├── dbt/                    # Models for daily marts
├── supabase/               # Schema, RLS policies, seed data
├── scripts/
│   ├── delete_org.py       # Full org deletion with receipt
│   ├── onboard.py          # Create org + first user
│   └── ops_check.py        # Scheduled health check
├── tests/
│   └── isolation/          # Cross-tenant isolation tests
├── eval/                   # Analyst evaluation set + runner
├── docs/
│   └── runbook.md          # Incident runbook
└── .github/workflows/      # Cron jobs + CI
```

---

## ⚙️ Configuration

<!-- TODO: confirm env variable names against .env.example -->
Create a `.env` file in the project root (mirrored in Render environment settings when deployed):

```
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_KEY=your_service_key
DATABASE_URL=postgresql://user:password@host:5432/dbname
GEMINI_API_KEY=your_gemini_api_key
ALLOWED_ORIGINS=http://localhost:8088
```

- Never commit secrets. Use GitHub Actions secrets and Render environment variables in deployment.

---

## 🚀 Getting Started

```bash
# Clone the repo
git clone https://github.com/Ayan-Ahmad-0/insight.git
cd insight

# Install dependencies
pip install -r requirements.txt

# Run the API locally
uvicorn api.main:app --reload

# Serve the web page locally
cd web && python -m http.server 8088

# Run the isolation tests
pytest tests/isolation
```

| Service | URL |
| --- | --- |
| Web (local) | http://localhost:8088 |
| API (local) | http://localhost:8000 |
| Web (live) | https://insight-1-g4j1.onrender.com |
| API (live) | https://insight-sxrc.onrender.com |

---

## 🚧 Challenges Solved

- Proved tenant isolation with automated attack tests that run in CI, instead of relying on policy review alone
- Used the analyst eval to catch three real bugs (guessed dates, wrong sums, a missing citation) and fixed each in the tools rather than the prompt alone
- Chose GitHub Actions cron over Airflow to keep orchestration hosted, free, and simple
- Fixed a CORS and localhost configuration issue between the Render static site and the API
- Worked around port 8080 being blocked on Windows by serving the web page on 8088
- Replaced a Discord alert webhook with an ops check that fails the GitHub Actions step visibly
<!-- TODO: add the Day 6 incident and what fixed it -->

---

## 🛠️ Future Improvements

- Self-serve CSV upload for customers
- Richer dashboard metrics and filters
- Larger eval set covering more than two test orgs
- Front-end handoff with published API documentation
<!-- TODO: add anything else planned -->

---

## 👤 Author

**Ayan Ahmad**: Data Engineer · [GitHub](https://github.com/Ayan-Ahmad-0)