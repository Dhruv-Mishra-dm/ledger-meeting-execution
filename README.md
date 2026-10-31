# Ledger — Meeting-to-Execution Agent (PS-03)

**Decisions made in meetings get lost.** Ledger takes a meeting, spoken with Wispr Flow or uploaded as a transcript, and:

1. keeps every line attributed to its speaker,
2. extracts **decisions, action items, owners and deadlines** with the transcript lines that support them,
3. stores decisions in a **persistent, per-project memory** with full history,
4. **detects conflicts** when a new meeting contradicts what was decided earlier, and makes a person resolve them,
5. publishes tasks to a **real tracker (GitHub Issues)** only after a person approves them,
6. sends **reminders** 24 hours before, on the due date and when overdue,
7. builds a **weekly digest for each person** from stored records.

> "The cross-meeting memory and the conflict detection are what make this a real system rather than a transcript summarizer." — Product Space PS-03

Product Space hackathon requirements and where each one lives:

| Requirement | Where it lives |
|---|---|
| Transcript ingestion with speaker attribution | TXT / DOCX / PDF upload and Wispr Flow dictation — `backend/app/ingest/parser.py` |
| Decisions, action items, owners, deadlines | `backend/app/ai/rules.py` (demo engine) and `ai/openai_compat.py` (Gemini or any OpenAI-compatible model) |
| Conflicts with earlier decisions in memory | `services/memory.py` and `services/conflicts.py` |
| Tasks created in a tracker through an integration | `trackers/github.py` (GitHub Issues) |
| Reminders before deadlines | `services/reminders.py` plus the APScheduler job |
| Weekly digest per person | `services/digest.py` |
| Confirmation before anything is posted | `services/review.py` and `services/publishing.py`, enforced on the server |
| Main input is speech through Wispr Flow | The "Speak with Wispr Flow" composer — see [docs/VOICE-WORKFLOW.md](docs/VOICE-WORKFLOW.md) |

---

## Start it on Windows (beginner steps)

You need **Python 3.11 or newer** ([python.org](https://www.python.org/downloads/), tick *Add python.exe to PATH* during install) and **Node.js 20 or newer** ([nodejs.org](https://nodejs.org)).

Open **PowerShell** in this folder (`ps-03-meeting-execution`). In File Explorer, click the address bar, type `powershell` and press Enter. Then run:

```powershell
# 1. One-time setup (installs packages, creates the database and demo accounts)
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

# 2. Start the app (opens two windows and your browser at http://localhost:5173)
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

Sign in as **Anshul** (manager) with password **`demo1234`**. The password is set by `DEMO_PASSWORD` in `backend\.env`.

| Account | Role | Can |
|---|---|---|
| Anshul | manager | upload, process, approve, reject, resolve conflicts, publish |
| Admin | admin | everything, all projects |
| Rahul, Priya, Karan | member | view their projects, complete their own tasks, see their own digest |

To stop the app, close the two PowerShell windows.

### Run the tests

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run-tests.ps1
```

### Reset the demo data

Close the backend window first, then:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\reset-demo.ps1             # empty project, ready for a live demo
powershell -ExecutionPolicy Bypass -File scripts\reset-demo.ps1 -Scenario   # fallback: all 3 meetings already processed
```

### Manual commands, if you prefer

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy ..\.env.example .env
.\.venv\Scripts\python.exe -m app.seed
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# in a second window:
cd frontend
npm install
npx vite --host 127.0.0.1
```

API documentation is generated live at <http://127.0.0.1:8000/docs> while the backend runs.

---

## Modes: what is real and what is demo

The app runs with **no keys at all**, and it always tells you which mode it is in.

| Part | Without keys (default) | With keys |
|---|---|---|
| AI engine | **Demo mode**: a deterministic rules engine that reads the actual transcript. It is not an LLM. A yellow "Demo mode" banner is shown, and every result is labelled `demo-rules`. | `AI_PROVIDER=openai` with Gemini or any OpenAI-compatible API. Responses are schema-validated and grounded against the transcript. |
| Task tracker | **Demo tracker**: records tasks inside the app, labelled "Simulated — not sent to any external service". | `TRACKER_PROVIDER=github` creates real GitHub issues. See [docs/TRACKER-INTEGRATION.md](docs/TRACKER-INTEGRATION.md). |

Configuration is in `backend\.env`. Every option is explained in [.env.example](.env.example).

---

## Documentation

- [docs/DEMO-GUIDE.md](docs/DEMO-GUIDE.md) — the three-meeting demonstration, click by click
- [docs/VOICE-WORKFLOW.md](docs/VOICE-WORKFLOW.md) — how Wispr Flow is used to build the product and to run it
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — design, decisions, data flow, tracker choice
- [docs/DATABASE.md](docs/DATABASE.md) · [docs/API.md](docs/API.md) · [docs/SECURITY.md](docs/SECURITY.md) · [docs/TESTING.md](docs/TESTING.md)
- [docs/TRACKER-INTEGRATION.md](docs/TRACKER-INTEGRATION.md) — GitHub Issues setup
- [docs/IMPLEMENTATION-STATUS.md](docs/IMPLEMENTATION-STATUS.md) — what is done, what has been verified, known limitations
- [docs/planning/](docs/planning/) — the original planning documents for this track (superseded where noted)

## Troubleshooting

| Symptom | Fix |
|---|---|
| `running scripts is disabled on this system` | Use the `powershell -ExecutionPolicy Bypass -File ...` form shown above. |
| `python` is not recognised | Reinstall Python and tick *Add to PATH*, or use `py` instead of `python`. |
| Login page says it cannot reach the server | The backend window must be running on port 8000. Check it for errors. |
| `Port 5173 is already in use` | Close the other frontend window, or any other app using that port. |
| Upload says "already uploaded" | Duplicate detection is working. Reset the demo, or use another project. |
| A meeting shows "Processing failed" with real AI | Check `AI_API_KEY`. Click **Use demo engine instead** to continue; the result is labelled accordingly. |
| GitHub "Test connection" fails | The token needs *Issues: Read and write* on exactly the repository named in `GITHUB_REPO` (`owner/name`). |
| Reminders do not appear | Deadlines are in November 2026. Use **Reminders → Demo clock** to set the app date (a banner shows while it is active). |
