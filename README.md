# MediAgent AI

A local hackathon prototype for clinician review, with an ER patient dashboard,
saved encounter reports, and MedlinePlus-backed medical reference search.

Team Techtonics: Apsara, Vaibhav Sharma, and Kajal Rajput.

## What it does

- Uses Ollama with `qwen2.5:3b` to classify current patient descriptions.
- Displays provisional priorities and a separate Needs assessment group.
- Keeps one public numeric patient ID across explicitly selected return visits.
- Saves each encounter and report in SQLite.
- Tracks Waiting, In care, and Completed care without deleting saved reports.
- Searches retained encounters by name, patient ID, or reference note.
- Retrieves MedlinePlus health-topic snippets and displays links with a local summary.

## Run on your laptop

Install Python and Ollama first. From your project folder:

```powershell
python -m pip install -r requirements.txt
ollama pull qwen2.5:3b
python -m streamlit run app.py
```

Keep Ollama running. Open the local URL printed by Streamlit, normally
`http://localhost:8501`. Downloading the model and searching MedlinePlus need
internet. Local classification can run once the model is installed.

### First launch: staff accounts

The first launch now asks you to create an administrator with your own password
(at least 10 characters). There are no default passwords or pre-created accounts.
Other users choose **Create account** on the welcome page and set their own
username, password and requested role. Their account remains pending until an
administrator verifies and approves access. Public sign-up cannot create an
administrator or grant clinical access automatically.

| Role | Access |
| --- | --- |
| Reception | Register patients for manual assessment and view basic registration details. Clinical reports are restricted. |
| Nurse / Doctor | View clinical reports and timelines, run AI classification, record a separate clinical decision, add observations, configure reminders, and update care status. |
| Administrator | Verify/approve account requests, link patient identities, disable accounts, inspect audit history, and view basic registration details. Use a separate clinical account for clinical work. |
| Patient | Read reports and visits linked to the account's patient ID, try the symptom check demo without saving a visit, and search general medical references. Cannot access staff dashboards, other patients, or staff actions. |

Select **Doctor, Nurse, Receptionist, Administrator, or Patient** on the sign-in
page. The selected role must match the account's stored role; it never grants
extra access. Existing staff accounts and passwords continue to work.

For a new staff sign-up, use **Staff accounts > Pending approvals**. For a patient
sign-up, use **Patient accounts > Pending approvals**. After verifying the person,
approve their login without linking, or link their existing numeric patient ID.
Use **Manage accounts** to link a verified patient record later. The administrator never
needs to know or choose the user's password. There is no self-service
record claiming by name or ID. Patients see their own visits, care status,
recorded clinical decision and separately labelled AI report. Patient accounts
can be disabled through Manage accounts. All signed-in users can use
**Change my password** in the sidebar, entering their current password and a new
one. This prototype does not yet provide forgotten-password recovery.

Sessions expire after eight hours. Signing out clears the current browser session's
patient selection and report data. Disabling an account or changing its password
revokes its existing sessions. Passwords use salted PBKDF2 hashes; session tokens
are stored as hashes in the local database.

### Staff workflow

Use **Navigation** in the sidebar to switch sections. Administrators have separate
Staff accounts, Patient accounts, Audit history, Patient dashboard and Medical
knowledge search pages. Account pages show either Pending approvals or Manage
accounts at a time. Clinical staff and reception see their permitted dashboard
and reference-search sections; patient accounts remain in their own portal.

Clinical navigation now separates **Patient dashboard**, **Register patient**,
**Patient report**, **Clinical review**, **Observations and reminders**, and
**Patient timeline**. Click a patient on the dashboard to open their report;
the selected visit carries across the clinical screens. Registration redirects
to the saved report (or reception's dashboard) without repeating the submission.
Reassessment reminders refresh on the Observations and reminders screen.

### Team-meeting additions

- **Richer intake:** Register patient includes tabs for current symptoms,
  medical history and recorded vitals. Onset, progression, pain score, breathing,
  responsiveness, allergies, medicines, conditions, procedures, pregnancy context,
  exposures and readings can be recorded. Blank/unknown fields stay unknown. The
  app does not measure vitals or implement a validated clinical scoring system.
  Additional intake is saved per visit and sent with that visit's symptoms to
  Ollama. A later retry uses the same saved intake. Old records migrate with an
  empty intake and retain their original reports.
- **Structured report:** Patient report displays recorded intake and the latest
  staff decision separately from AI output. Download structured report exports a
  Markdown document. Patient portal users can download their own visit reports.
- **Previous reports and history:** Patient history shows every visit for the
  selected patient, including recorded medical history, care status and priority.
  Open report selects that exact visit's saved report without calling the model.
  Prior visit reports remain immutable; prior symptoms are not assumed current.
- **Voice search:** Medical knowledge search > Use voice to enter a reference
  question > Enable browser voice input. Choose a language, start the microphone,
  stop, review the transcript and click Use this transcript. Edit the normal
  question box before submitting Search Medical Database. No search runs merely
  from recording. SpeechRecognition availability depends on the browser and
  microphone permissions. The browser may send audio to its speech provider and
  require internet; this is not offline Ollama speech recognition. The Python app
  receives transcript text only, not audio. Use non-identifying reference questions.
  If voice input is unavailable, typed search continues to work.
- **Emergency help:** Open emergency guide is always available in the sidebar,
  including before login. The India contact is 112 (integrated police, fire and
  medical emergency services); outside India the app directs users to their local
  emergency number. Static general guidance links to official sources and works
  without Ollama. Desktop `tel:` links depend on the device having a calling app.

Source references checked 1 November 2026:
[India ERSS](https://112.gov.in/faq),
[Resuscitation Council UK first aid](https://www.resus.org.uk/professional-library/2025-resuscitation-guidelines/first-aid-guidelines),
[browser SpeechRecognition privacy and compatibility](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition).
The general first-aid text uses the local emergency-number selection rather than
copying the UK emergency number into the India interface.

- **Manual assessment:** select "Save for manual assessment (skip AI)" before
  submitting a patient. Reception always uses this path. Failed/pending AI visits
  remain visible and can receive a manual staff decision without Ollama.
- **Clinical review:** open a patient and accept the AI suggestion or record a
  different priority, with a reason. The AI report remains separate and unchanged.
  Dashboard sorting uses the latest recorded staff priority when available and
  otherwise the AI suggestion. Unknown priorities stay in Needs assessment.
- **Observations:** add notes or recorded vitals to the patient's timeline. Checking
  the reassessment box updates the last-assessed timestamp. Notes do not rewrite
  the original intake or silently rerun the model.
- **Reminders:** save a staff-chosen interval per encounter. No clinical schedule
  is assigned automatically. The clock starts at arrival or last assessment.
  Reminders refresh every 20 seconds while the clinical page is open; there are
  no background, email, or phone alerts. Completed care does not trigger reminders.
- **Timeline:** select "Load patient timeline" to see visits, saved reports,
  observations, reviews, name changes and care-status changes across the patient's
  visits. Records from before this update show known visit timestamps without
  invented historical activity.
- **Audit:** administrators can load the latest 250 events with actor, time and
  change details. Registration, AI results/failures, reviews, changes, and dashboard,
  report and timeline access are logged. Mutations and their audit entries commit
  together. This is an application audit log, not a tamper-proof forensic system.

See [the short demo guide](docs/Staff_Workflow_Demo.md) for a walkthrough.

Cloning this repository downloads the code and documents. It does not install
Python packages or Ollama, download model weights, or start the app automatically.

## Data storage

The app creates `data/triage.sqlite3` automatically. This local database is excluded
from Git. Each teammate gets their own database when they run their local copy.
Completing care retains the encounter and report. Return visits share the selected
patient ID, while encounter keys stay internal.

Use `MEDIAGENT_DB_PATH` to select a separate database for tests or demonstrations.
Never upload real patient data or credentials to this repository.

## Project files

- `app.py`: Streamlit interface, workflow, model request and MedlinePlus retrieval.
- `safety_classifier.py`: classification prompt, schema, parsing and correction.
- `patient_store.py`: SQLite storage, migration, identity, search and care status.
- `staff_workflow.py`: authentication, role-checked services, reviews, reminders, timeline and audit events.
- `staff_ui.py`: sign-in, staff administration and clinical workflow screens.
- `clinical_features.py`: intake form, structured report export and emergency guide.
- `voice_search.py` / `voice_component/`: opt-in browser dictation and transcript handoff.
- `test_*.py`: automated software checks.
- `docs/`: team learning guide and hackathon presentation.
- [CONTRIBUTING.md](CONTRIBUTING.md): beginner instructions for GitHub, updates and collaboration.

## Tests

```powershell
python -m unittest discover -v
```

Tests use temporary databases and controlled model responses. They verify software
behavior, not clinical accuracy. The MedlinePlus parser tests currently target an
extracted helper copy, so production retrieval coverage remains limited.

## Prototype limits

This is not a validated triage system, suicide-risk assessment, diagnostic tool,
or comprehensive drug-reference database. Model classifications and source-based
summaries can be wrong. A qualified person must review the full context. Possible
emergencies must not wait for model output.

The app has local role-based login and application audit logging, but no database
encryption, login rate limiting, MFA, tamper-proof audit storage or secure shared
deployment. Anyone with direct access to the SQLite file or application code can
bypass application permissions. Secure the laptop and do not expose this prototype
to the public internet. Use fictional or de-identified demo records. Names are stored locally for search but any identifying
text entered in the clinical description still reaches the configured local model.
Clinical validation, secure shared deployment and stronger evaluation remain future work.
