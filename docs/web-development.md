# Next.js frontend and FastAPI backend

The web workspace uses Next.js App Router, React, and TypeScript. FastAPI
exposes the existing `clear_app.contract.Clear` service, so agents,
calculations, validation, approval, and STO creation use the same business
logic as the Streamlit demo.

```text
Browser -> Next.js /api/clear/* proxy -> FastAPI -> Clear
                                               -> agents and tools
                                               -> local JSON or AWS store
```

The browser uses a relative URL on the Next.js origin. The destination API
address is a server-side setting, so no SAP or AWS credentials belong in the
frontend. The proxy also avoids needing browser CORS configuration for this
setup.

## Install

Use Python 3.12 or newer and Node.js 22 LTS. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[api,dev]"
```

The `dev` extra pins Strands to the version in the deployment bundle,
because the test suite requires those versions to match. The `api` extra
installs FastAPI and Uvicorn. For the gateway configuration, also install
the existing `aws` extra:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[api,dev,aws]"
```

Then install the frontend dependencies:

```powershell
cd frontend
npm ci
```

On macOS/Linux, use `.venv/bin/python` instead of
`.venv\Scripts\python.exe`. The following start commands assume PowerShell.

## Run without credentials

In terminal 1, at the repository root:

```powershell
$env:CLEAR_UI_SCRIPTED = "1"
.\.venv\Scripts\python.exe -m uvicorn clear_app.api:create_app --factory --host 127.0.0.1 --port 8000
```

In terminal 2:

```powershell
cd frontend
npm run dev
```

Open `http://127.0.0.1:3000/workspace` (the landing page is at `/`). API documentation is at
`http://127.0.0.1:8000/docs`.

The API initializes local runtime data from the seed only when the runtime
directory does not exist. Scripted mode forces baseline duration prediction
and ignores gateway/runtime configuration, so the development workflow does
not need credentials. Its visible banner distinguishes predefined agent
responses from live model reasoning.

## Exercise the workflow

1. Send **Customs document hold**. Review the evidence, shortage, rejected
   full-transfer validation, partial-transfer option, and demand priorities.
2. Open **Documents** to inspect highlighted discrepancies and **Inventory**
   to inspect stock, safety thresholds, consumption, and demand orders.
3. Open **Approval**. Select a fictional demo planner and approve the
   validated transfer, or enter a note and reject it.
4. After approval, the activity feed records STO creation and stock
   verification. The case moves to monitoring.
5. Send **Vessel ETA changed** to reassess the existing S1 case.
6. Send **Port congestion** for S2. With the seeded inventory, the current
   plan is covered and no transfer is needed.

The frontend polls the API every two seconds, without overlapping polling
cycles. It requests only log entries after the last sequence number and
aborts obsolete requests when the selected case changes. Connection errors
leave a visible stale-data notice and disable decisions until updates
recover. Errors from mutations are displayed separately. The API returns
`409` when another run is already using the store.

The planner selector labels an audit record; it is not authentication.
This demo uses loopback-only start commands and assumes trusted local
operators. External deployment needs authenticated identities and access
controls before enabling remote approvals.

## Use live agents or AWS tools

Configure the root `.env` using [setup.md](setup.md). Set
`CLEAR_UI_SCRIPTED=0` in the API process to use live agents. The API loads
the root `.env`; values already set in the process take precedence.

The backend selection follows the existing demo:

| Configuration | Agents | Tools and data |
|---|---|---|
| `CLEAR_UI_SCRIPTED=1` | Scripted model in this process | Local JSON, baseline prediction |
| No runtime ARN or gateway URL | Live model in this process | Local JSON |
| Gateway URL configured | Live model in this process | AgentCore Gateway, Lambda, DynamoDB |
| Runtime ARN configured | AgentCore Runtime | Existing remote store and tool integration |

Runtime ARN takes precedence over the gateway URL. The Runtime option is
supported by the existing code; it does not imply that the team's AWS
account currently has Runtime quota. This migration does not deploy or
change AWS resources.

`GET /health` reports process status, configured engines, mode, and whether
a run is active. It is not a live readiness probe of SAP or AWS.

## Addresses and deployment constraints

Next.js defaults to `http://127.0.0.1:8000` for the API destination. Copy
`frontend/.env.example` to `frontend/.env.local` to change `CLEAR_API_URL`.
That variable is server-side; it must resolve from the Next.js server to
the FastAPI service. Restart Next.js after a development change, and set
the value before a production build because the rewrite is built into the
Next.js configuration.

Run the API as one process with one worker per data store. The current
single-writer lock is process-local. Do not run Streamlit, a second API
worker, or CLI agent runs against the same runtime store at the same time.
In the gateway configuration the SAP Joule path uses the same DynamoDB
table: a case started or approved in Joule shows up in the workspace through
its polling, and runs should start from one front door at a time.
Do not use automatic reload during an active case run. API shutdown waits
for the current background thread to finish; a forced process termination
can still interrupt it. Durable background jobs and recovery after a
process crash are outside this adapter's scope.

The Streamlit entry point remains available for the existing workflow.
The Next.js frontend does not expose a data-reset endpoint. To reset local
demo data, stop the app processes first and run the existing command:

```powershell
.\.venv\Scripts\python.exe scripts/reset_data.py
```

This command replaces local runtime state with the seed. Cloud reset is
still governed by the existing AWS workflow in [setup.md](setup.md).

## Build and checks

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

API tests run when the `api` extra is installed; otherwise that test module
is skipped. They cover S1 approval and execution, ETA reassessment, S2
without a write, rejection validation, case binding, stale approvals,
unknown IDs, incremental log cursors, and concurrent-run rejection.

From `frontend/`:

```powershell
npm run build
npm run typecheck
npx playwright install chromium
npm run test:e2e
```

The browser tests start isolated services on ports 8101 and 3101 and use a
new runtime under `frontend/.test-runtime/`, without live credentials. Set
`CLEAR_E2E_API_PORT` and `CLEAR_E2E_WEB_PORT` to override these ports. The
frontend uses `.next-e2e/` so tests can run alongside the normal dev server.
`CLEAR_NEXT_DIST_DIR` selects a separate Next.js build directory when needed.
The workflow test exercises event submission, document discrepancies, inventory, approval,
STO confirmation, ETA reassessment, and a covered case. It also checks the
mobile viewport, branded loading, reduced-motion behavior, document source
comparisons, and local approval errors. A second test checks interrupted
connections, recovery, and keyboard tab navigation. Screenshots are recorded
in `frontend/test-results/`.
Those generated directories are ignored by Git.

For a production frontend build, run `npm run build` and `npm start` in
`frontend/`, alongside the separately running API process.
