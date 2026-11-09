"""Local encounter storage. Uses short-lived connections, never a shared UI connection."""
import json
import re
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
from datetime import datetime, timezone

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "triage.sqlite3"
WORKFLOW_SCHEMA_VERSION = 2


def database_path():
    return Path(os.environ.get("MEDIAGENT_DB_PATH", DEFAULT_DB_PATH))


@contextmanager
def _connect():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS encounters (
                id TEXT PRIMARY KEY, reference TEXT NOT NULL, created_at TEXT NOT NULL,
                age INTEGER NOT NULL, gender TEXT NOT NULL, symptoms TEXT NOT NULL,
                model TEXT NOT NULL, status TEXT NOT NULL,
                classification TEXT, error TEXT
            )""")
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(encounters)")}
            # Additive migration preserves all existing encounters and reports.
            for column, definition in {
                "patient_name": "TEXT NOT NULL DEFAULT ''",
                "care_status": "TEXT NOT NULL DEFAULT 'Waiting'",
                "completed_at": "TEXT",
                "patient_id": "INTEGER",
                "visit_code": "TEXT",
                "visit_type": "TEXT NOT NULL DEFAULT 'New patient'",
                "intake_json": "TEXT NOT NULL DEFAULT '{}'",
            }.items():
                if column not in columns:
                    connection.execute(f"ALTER TABLE encounters ADD COLUMN {column} {definition}")
            connection.execute("CREATE TABLE IF NOT EXISTS patients (id INTEGER PRIMARY KEY AUTOINCREMENT)")
            # Patient IDs are the only public identifier: numeric, starting at 10001.
            next_number = max(10000, connection.execute("SELECT COALESCE(MAX(id), 0) FROM patients").fetchone()[0])
            for row in connection.execute("SELECT id FROM patients WHERE id < 10000 ORDER BY id").fetchall():
                next_number += 1
                connection.execute("UPDATE patients SET id=? WHERE id=?", (next_number, row["id"]))
                connection.execute("UPDATE encounters SET patient_id=? WHERE patient_id=?", (next_number, row["id"]))
            connection.execute("INSERT INTO sqlite_sequence(name, seq) SELECT 'patients', 10000 WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name='patients')")
            connection.execute("UPDATE sqlite_sequence SET seq=MAX(seq, 10000) WHERE name='patients'")
            connection.execute("CREATE TABLE IF NOT EXISTS sequences (name TEXT PRIMARY KEY, value INTEGER NOT NULL)")
            # Old encounters cannot be linked by name alone: assign separate patient IDs.
            for row in connection.execute("SELECT id, patient_id, visit_code FROM encounters WHERE patient_id IS NULL OR visit_code IS NULL ORDER BY created_at, id").fetchall():
                patient_id = row["patient_id"]
                if patient_id is None:
                    patient_id = connection.execute("INSERT INTO patients DEFAULT VALUES").lastrowid
                code = row["visit_code"] or _next_visit_code(connection)
                connection.execute("UPDATE encounters SET patient_id=?, visit_code=? WHERE id=?",
                                   (patient_id, code, row["id"]))
            # Shorten display codes without changing legacy primary keys or patient links.
            for row in connection.execute("SELECT id, reference, visit_code FROM encounters WHERE visit_code LIKE 'V0%'").fetchall():
                if re.fullmatch(r"V0[0-9]+", row["visit_code"]):
                    short_code = "V" + str(int(row["visit_code"][1:]))
                    reference = short_code if row["reference"] == row["visit_code"] else row["reference"]
                    connection.execute("UPDATE encounters SET visit_code=?, reference=? WHERE id=?",
                                       (short_code, reference, row["id"]))
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS encounter_visit_code ON encounters(visit_code)")
            yield connection
    finally:
        connection.close()


def _next_visit_code(connection):
    connection.execute("INSERT OR IGNORE INTO sequences VALUES ('visit', 0)")
    connection.execute("UPDATE sequences SET value=value+1 WHERE name='visit'")
    number = connection.execute("SELECT value FROM sequences WHERE name='visit'").fetchone()[0]
    return f"V{number}"


def patient_code(patient_id):
    return str(patient_id)


def create_encounter(patient, model, reference="", patient_name="", existing_patient_id=None, actor=None):
    created = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    with _connect() as connection:
        if actor:
            from staff_workflow import authorize_actor, CLINICAL
            authorize_actor(connection, actor, ('Reception',)+CLINICAL)
        if existing_patient_id is None:
            patient_id = connection.execute("INSERT INTO patients DEFAULT VALUES").lastrowid
            visit_type = "New patient"
        else:
            if connection.execute("SELECT id FROM patients WHERE id=?", (existing_patient_id,)).fetchone() is None:
                raise ValueError("Existing patient ID was not found")
            patient_id = existing_patient_id
            visit_type = "Returning patient"
        encounter_id = _next_visit_code(connection)
        reference = reference.strip()
        connection.execute(
            """INSERT INTO encounters
                (id, reference, created_at, age, gender, symptoms, model, status, classification, error,
                 patient_name, patient_id, visit_code, visit_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (encounter_id, reference, created, patient["age"], patient["gender"],
             patient["symptoms"], model, "Pending", None, None, patient_name.strip(),
             patient_id, encounter_id, visit_type),
        )
        connection.execute('UPDATE encounters SET intake_json=? WHERE id=?',
                           (json.dumps(patient.get('intake', {}), ensure_ascii=False), encounter_id))
        if actor:
            from staff_workflow import _event
            _event(connection, actor, 'Patient registered', {'id': encounter_id, 'patient_id': patient_id},
                   dict(visit_type=visit_type, age=patient['age'], gender=patient['gender'],
                        symptoms=patient['symptoms'], intake=patient.get('intake', {}),
                        patient_name=patient_name.strip(), reference=reference))
    return encounter_id


def finish_encounter(encounter_id, classification=None, error=None, actor=None):
    if (classification is None) == (error is None):
        raise ValueError("Supply either a classification or a failure reason")
    with _connect() as connection:
        if actor:
            from staff_workflow import authorize_actor, CLINICAL
            authorize_actor(connection, actor, CLINICAL)
        before = get_row(connection, encounter_id)
        if actor and before['classification']:
            raise ValueError('The saved AI report is retained. Record a staff review separately.')
        cursor = connection.execute(
            "UPDATE encounters SET status=?, classification=?, error=? WHERE id=?",
            ("Complete" if classification is not None else "Failed",
             json.dumps(classification, ensure_ascii=False) if classification is not None else None,
             error, encounter_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("Encounter was not found")
        if actor:
            from staff_workflow import _event
            _event(connection, actor, 'AI report saved' if classification else 'AI classification failed', before,
                   dict(classification=classification, error=error))


def _decode(row):
    if row is None:
        return None
    result = dict(row)
    result["classification"] = json.loads(result["classification"]) if result["classification"] else None
    result['intake'] = json.loads(result.get('intake_json') or '{}')
    return result


def get_encounter(encounter_id):
    with _connect() as connection:
        return _decode(connection.execute("SELECT * FROM encounters WHERE id=?", (encounter_id,)).fetchone())


def list_encounters():
    with _connect() as connection:
        return [_decode(row) for row in connection.execute("SELECT * FROM encounters ORDER BY created_at, id")]


CARE_STATUSES = ("Waiting", "In care", "Completed")


def get_row(connection, encounter_id):
    row = connection.execute('SELECT * FROM encounters WHERE id=?', (encounter_id,)).fetchone()
    if row is None:
        raise ValueError('Encounter was not found')
    return dict(row)


def update_care_status(encounter_id, care_status, actor=None):
    if care_status not in CARE_STATUSES:
        raise ValueError("Invalid care status")
    with _connect() as connection:
        if actor:
            from staff_workflow import authorize_actor, CLINICAL
            authorize_actor(connection, actor, CLINICAL)
        before = get_row(connection, encounter_id)
        cursor = connection.execute(
            """UPDATE encounters SET care_status=?,
               completed_at=CASE WHEN ?='Completed' THEN COALESCE(completed_at, ?) ELSE NULL END
               WHERE id=?""",
            (care_status, care_status, datetime.now(timezone.utc).isoformat(), encounter_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("Encounter was not found")
        if actor:
            from staff_workflow import _event
            _event(connection, actor, 'Care status changed', before,
                   dict(before=before['care_status'], after=care_status))


def update_patient_name(encounter_id, patient_name, actor=None):
    with _connect() as connection:
        if actor:
            from staff_workflow import authorize_actor, CLINICAL
            authorize_actor(connection, actor, ('Reception',)+CLINICAL)
        before = get_row(connection, encounter_id)
        cursor = connection.execute("UPDATE encounters SET patient_name=? WHERE id=?",
                                    (patient_name.strip(), encounter_id))
        if cursor.rowcount != 1:
            raise ValueError("Encounter was not found")
        if actor:
            from staff_workflow import _event
            _event(connection, actor, 'Patient name changed', before,
                   dict(before=before['patient_name'], after=patient_name.strip()))


def filter_encounters(records, search="", view="All patients"):
    query = search.strip().casefold()
    return [r for r in records
            if (not query or query in r["patient_name"].casefold() or query in r["reference"].casefold()
                or query in patient_code(r["patient_id"]).casefold())
            and (view != "Active patients" or r["care_status"] != "Completed")
            and (view != "Completed patients" or r["care_status"] == "Completed")]


def dashboard_groups(records):
    """Keep unclassified/uncertain encounters separate from the provisional priority queue."""
    rank = {"Critical": 0, "Urgent": 1, "Non-urgent": 2}
    classified, assessment = [], []
    for record in records:
        if record.get("care_status") == "Completed":
            continue
        result = record.get('review') or record["classification"]
        if not result or result["priority"] not in rank:
            assessment.append(record)
        else:
            classified.append(record)
    classified.sort(key=lambda r: (rank[(r.get('review') or r["classification"])["priority"]],
                                    not (r.get('classification') or {}).get('immediate_emergency', False), r["created_at"], r["id"]))
    assessment.sort(key=lambda r: (r["created_at"], r["id"]))
    return classified, assessment
