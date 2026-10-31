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

The app has no login, database encryption or complete audit trail. Use fictional
or de-identified demo records. Names are stored locally for search but any identifying
text entered in the clinical description still reaches the configured local model.
Clinical validation, secure shared deployment and stronger evaluation remain future work.
