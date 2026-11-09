"""Authenticated application services for the local staff-workflow prototype.

All UI data access goes through this module. patient_store is the internal persistence
layer, not an independently secured API. Anyone with direct access to the SQLite file
can bypass application permissions; this is not a production security boundary.
"""
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

import patient_store as store

ROLES = ("Reception", "Nurse", "Doctor", "Administrator")
ACCOUNT_ROLES = ROLES + ('Patient',)
CLINICAL = ("Nurse", "Doctor")
PRIORITIES = ("Critical", "Urgent", "Non-urgent", "Unable to determine")


def now():
    return datetime.now(timezone.utc)


def initialize():
    with store._connect() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS staff (
                id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL, role TEXT NOT NULL,
                salt TEXT NOT NULL, password_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS staff_sessions (
                token_hash TEXT PRIMARY KEY, staff_id INTEGER NOT NULL, expires_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS workflow_events (
                id INTEGER PRIMARY KEY, encounter_id TEXT, patient_id INTEGER,
                actor_id INTEGER, actor_name TEXT NOT NULL, actor_role TEXT NOT NULL,
                action TEXT NOT NULL, occurred_at TEXT NOT NULL, details TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS workflow_patient_events ON workflow_events(patient_id, occurred_at);
            CREATE TABLE IF NOT EXISTS clinician_reviews (
                id INTEGER PRIMARY KEY, encounter_id TEXT NOT NULL, actor_id INTEGER NOT NULL,
                actor_name TEXT NOT NULL, actor_role TEXT NOT NULL, created_at TEXT NOT NULL,
                decision TEXT NOT NULL, priority TEXT NOT NULL, reason TEXT NOT NULL);
        """)
        staff_columns = {r['name'] for r in db.execute('PRAGMA table_info(staff)')}
        if 'patient_id' not in staff_columns:
            db.execute('ALTER TABLE staff ADD COLUMN patient_id INTEGER')
        if 'approval_state' not in staff_columns:
            db.execute("ALTER TABLE staff ADD COLUMN approval_state TEXT NOT NULL DEFAULT 'Approved'")
        columns = {r['name'] for r in db.execute('PRAGMA table_info(encounters)')}
        for name, definition in {'review_interval_minutes': 'INTEGER', 'last_reviewed_at': 'TEXT'}.items():
            if name not in columns:
                db.execute(f'ALTER TABLE encounters ADD COLUMN {name} {definition}')


def _event(db, actor, action, encounter=None, details=None):
    db.execute('''INSERT INTO workflow_events
        (encounter_id,patient_id,actor_id,actor_name,actor_role,action,occurred_at,details)
        VALUES (?,?,?,?,?,?,?,?)''',
        (encounter['id'] if encounter else None, encounter['patient_id'] if encounter else None,
         actor['id'], actor['display_name'], actor['role'], action, now().isoformat(),
         json.dumps(details or {}, ensure_ascii=False)))


def _password(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 310000).hex()


def _new_staff(db, username, display_name, role, password):
    username = username.strip().casefold()
    if not username or not display_name.strip() or role not in ACCOUNT_ROLES:
        raise ValueError('Enter a username, display name and valid role.')
    if len(username) > 80 or len(display_name) > 120 or len(password) < 10 or len(password) > 256:
        raise ValueError('Use a password of 10-256 characters and shorter account names.')
    salt = secrets.token_hex(16)
    cursor = db.execute('INSERT INTO staff(username,display_name,role,salt,password_hash) VALUES(?,?,?,?,?)',
                        (username, display_name.strip(), role, salt, _password(password, salt)))
    return cursor.lastrowid


def needs_setup():
    initialize()
    with store._connect() as db:
        return db.execute('SELECT COUNT(*) FROM staff').fetchone()[0] == 0


def bootstrap_admin(username, display_name, password):
    initialize()
    with store._connect() as db:
        # _connect's sequence migration already opens a write transaction,
        # serializing concurrent first-account creation before this check.
        if db.execute('SELECT COUNT(*) FROM staff').fetchone()[0]:
            raise ValueError('Initial administrator already exists. Sign in.')
        uid = _new_staff(db, username, display_name, 'Administrator', password)
        actor = dict(id=uid, display_name=display_name.strip(), role='Administrator')
        _event(db, actor, 'Initial administrator created')


def login(username, password, expected_role=None):
    initialize()
    with store._connect() as db:
        row = db.execute('SELECT * FROM staff WHERE username=?', (username.strip().casefold(),)).fetchone()
        # Perform a password derivation even for unknown accounts.
        candidate = _password(password, row['salt'] if row else '00' * 16)
        if row is None or not hmac.compare_digest(candidate, row['password_hash']):
            raise ValueError('Invalid username or password.')
        if row['approval_state'] == 'Pending':
            raise ValueError('Your account is awaiting identity verification and approval. Your password was accepted.')
        if not row['active']:
            raise ValueError('This account is disabled. Contact your administrator.')
        if expected_role is not None and (expected_role not in ACCOUNT_ROLES or row['role'] != expected_role):
            raise ValueError('These credentials do not match the selected sign-in role.')
        token = secrets.token_urlsafe(32)
        db.execute('DELETE FROM staff_sessions WHERE expires_at<=?', (now().isoformat(),))
        db.execute('INSERT INTO staff_sessions VALUES(?,?,?)',
                   (hashlib.sha256(token.encode()).hexdigest(), row['id'], (now()+timedelta(hours=8)).isoformat()))
        _event(db, dict(row), 'Signed in')
        return token


def _actor(db, token, roles=ROLES):
    row = db.execute('''SELECT staff.* FROM staff JOIN staff_sessions s ON s.staff_id=staff.id
        WHERE s.token_hash=? AND s.expires_at>? AND staff.active=1''',
        (hashlib.sha256((token or '').encode()).hexdigest(), now().isoformat())).fetchone()
    if row is None:
        raise PermissionError('Please sign in again.')
    if row['role'] not in roles:
        raise PermissionError('Your staff role cannot perform this action.')
    result = dict(row)
    result['_session_hash'] = hashlib.sha256((token or '').encode()).hexdigest()
    return result


def authorize_actor(db, actor, roles):
    """Recheck the session inside the same transaction as a persistence write."""
    row = db.execute('''SELECT staff.id FROM staff JOIN staff_sessions s ON s.staff_id=staff.id
        WHERE staff.id=? AND staff.active=1 AND staff.role=? AND s.token_hash=? AND s.expires_at>?''',
        (actor['id'], actor['role'], actor.get('_session_hash', ''), now().isoformat())).fetchone()
    if row is None or actor['role'] not in roles:
        raise PermissionError('Your session or permission has changed. Sign in again.')


def current_user(token):
    with store._connect() as db:
        actor = _actor(db, token, ACCOUNT_ROLES)
        return {k: actor[k] for k in ('id', 'username', 'display_name', 'role', 'patient_id')}


def logout(token):
    with store._connect() as db:
        _actor(db, token, ACCOUNT_ROLES)
        db.execute('DELETE FROM staff_sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))


def create_staff(token, username, display_name, role, password):
    if role not in ROLES:
        raise ValueError('Use the linked patient-account form for patient access.')
    with store._connect() as db:
        actor = _actor(db, token, ('Administrator',))
        uid = _new_staff(db, username, display_name, role, password)
        _event(db, actor, 'Staff account created', details=dict(staff_id=uid, username=username, role=role))


def list_staff(token):
    with store._connect() as db:
        _actor(db, token, ('Administrator',))
        return [dict(r) for r in db.execute('SELECT id,username,display_name,role,active,patient_id,approval_state FROM staff ORDER BY id')]


def sign_up(username, display_name, role, password):
    """Public registration cannot activate permissions, choose an admin role or claim a patient ID."""
    initialize()
    if role not in ('Reception', 'Nurse', 'Doctor', 'Patient'):
        raise ValueError('Self-sign-up is available for staff and patients, not administrators.')
    with store._connect() as db:
        if not db.execute('SELECT 1 FROM staff WHERE role=?', ('Administrator',)).fetchone():
            raise ValueError('Complete the first-time administrator setup first.')
        uid = _new_staff(db, username, display_name, role, password)
        db.execute("UPDATE staff SET active=0,approval_state='Pending' WHERE id=?", (uid,))
        _event(db, dict(id=uid, display_name=display_name.strip(), role=role), 'Self-sign-up submitted',
               details=dict(account_id=uid, requested_role=role))


def approve_account(token, staff_id, patient_id=None, *, allow_unlinked=False):
    with store._connect() as db:
        actor = _actor(db, token, ('Administrator',))
        account = db.execute('SELECT * FROM staff WHERE id=?', (staff_id,)).fetchone()
        if account is None or account['approval_state'] != 'Pending':
            raise ValueError('Select a pending account.')
        if account['role']=='Patient':
            if patient_id is None and not allow_unlinked:
                raise ValueError('Verify identity and link an existing patient ID before approving.')
            if patient_id is not None and not db.execute('SELECT 1 FROM patients WHERE id=?', (patient_id,)).fetchone():
                raise ValueError('Select an existing patient ID.')
        else:
            patient_id = None
        updated = db.execute("""UPDATE staff SET active=1,approval_state='Approved',patient_id=?
            WHERE id=? AND approval_state='Pending'""", (patient_id, staff_id))
        if updated.rowcount != 1:
            raise ValueError('This account has already been reviewed.')
        _event(db, actor, 'Self-sign-up approved', details=dict(account_id=staff_id, role=account['role'], patient_id=patient_id))


def link_patient_account(token, account_id, patient_id):
    with store._connect() as db:
        actor = _actor(db, token, ('Administrator',))
        if not db.execute('SELECT 1 FROM patients WHERE id=?', (patient_id,)).fetchone():
            raise ValueError('Select an existing patient ID.')
        updated = db.execute("""UPDATE staff SET patient_id=? WHERE id=? AND role='Patient'
            AND approval_state='Approved' AND patient_id IS NULL""", (patient_id, account_id))
        if updated.rowcount != 1:
            raise ValueError('This account is no longer available for linking. Refresh and try again.')
        _event(db, actor, 'Patient portal record linked', details=dict(account_id=account_id, patient_id=patient_id))


def change_own_password(token, current_password, new_password):
    with store._connect() as db:
        actor = _actor(db, token, ACCOUNT_ROLES)
        if not hmac.compare_digest(_password(current_password, actor['salt']), actor['password_hash']):
            raise ValueError('Current password is incorrect.')
        if not 10<=len(new_password)<=256:
            raise ValueError('Use a password of 10-256 characters.')
        salt = secrets.token_hex(16)
        db.execute('UPDATE staff SET salt=?,password_hash=? WHERE id=?',
                   (salt, _password(new_password, salt), actor['id']))
        db.execute('DELETE FROM staff_sessions WHERE staff_id=?', (actor['id'],))
        _event(db, actor, 'Own password changed')


def create_patient_account(token, username, display_name, password, patient_id):
    with store._connect() as db:
        actor = _actor(db, token, ('Administrator',))
        if db.execute('SELECT id FROM patients WHERE id=?', (patient_id,)).fetchone() is None:
            raise ValueError('Select an existing patient ID.')
        uid = _new_staff(db, username, display_name, 'Patient', password)
        db.execute('UPDATE staff SET patient_id=? WHERE id=?', (patient_id, uid))
        _event(db, actor, 'Patient portal account created', details=dict(account_id=uid, patient_id=patient_id))


def patient_reports(token, encounter_id=None):
    """Patient identity comes only from the authenticated account, never a UI selector."""
    with store._connect() as db:
        actor = _actor(db, token, ('Patient',))
        if actor['patient_id'] is None:
            raise PermissionError('This account has no linked patient record. Contact the administrator.')
        rows = db.execute('''SELECT * FROM encounters WHERE patient_id=?
            AND (? IS NULL OR id=?) ORDER BY created_at DESC,id DESC''',
            (actor['patient_id'], encounter_id, encounter_id)).fetchall()
        if encounter_id is not None and not rows:
            raise ValueError('Report was not found for your account.')
        result = []
        for row in rows:
            r = store._decode(row)
            item = {k:r[k] for k in ('id','patient_id','patient_name','age','gender','symptoms',
                                      'created_at','care_status','classification','visit_type','intake')}
            review = db.execute('''SELECT priority,reason,created_at FROM clinician_reviews
                WHERE encounter_id=? ORDER BY id DESC LIMIT 1''', (r['id'],)).fetchone()
            item['review'] = dict(review) if review else None
            result.append(item)
            _event(db, actor, 'Own patient report viewed', r)
        return result


def set_staff_active(token, staff_id, active):
    with store._connect() as db:
        actor = _actor(db, token, ('Administrator',))
        if staff_id == actor['id']:
            raise ValueError('You cannot disable your own account.')
        account = db.execute('SELECT approval_state FROM staff WHERE id=?', (staff_id,)).fetchone()
        if account and account['approval_state']=='Pending':
            raise ValueError('Review and approve this pending sign-up first.')
        if db.execute('UPDATE staff SET active=? WHERE id=?', (int(active), staff_id)).rowcount != 1:
            raise ValueError('Staff account was not found.')
        db.execute('DELETE FROM staff_sessions WHERE staff_id=?', (staff_id,))
        _event(db, actor, 'Staff access updated', details=dict(staff_id=staff_id, active=bool(active)))


def return_patient_account_to_review(token, account_id, linked_patient_id):
    """Remove access to a linked record and require the account to be verified again."""
    with store._connect() as db:
        actor = _actor(db, token, ('Administrator',))
        updated = db.execute("""UPDATE staff SET active=0, approval_state='Pending', patient_id=NULL
            WHERE id=? AND role='Patient' AND approval_state='Approved' AND patient_id=?""",
            (account_id, linked_patient_id))
        if updated.rowcount != 1:
            raise ValueError('This patient link has changed. Refresh and review the account again.')
        db.execute('DELETE FROM staff_sessions WHERE staff_id=?', (account_id,))
        _event(db, actor, 'Patient portal access returned to review',
               details=dict(account_id=account_id, previous_patient_id=linked_patient_id))


def reset_password(token, staff_id, password):
    with store._connect() as db:
        actor = _actor(db, token, ('Administrator',))
        if not 10 <= len(password) <= 256:
            raise ValueError('Use a password of 10-256 characters.')
        salt = secrets.token_hex(16)
        if db.execute('UPDATE staff SET salt=?,password_hash=? WHERE id=?',
                      (salt, _password(password, salt), staff_id)).rowcount != 1:
            raise ValueError('Staff account was not found.')
        db.execute('DELETE FROM staff_sessions WHERE staff_id=?', (staff_id,))
        _event(db, actor, 'Staff password reset', details=dict(staff_id=staff_id))


def _encounter(db, encounter_id):
    row = db.execute('SELECT * FROM encounters WHERE id=?', (encounter_id,)).fetchone()
    if row is None:
        raise ValueError('Patient encounter was not found.')
    return store._decode(row)


def records(token):
    with store._connect() as db:
        actor = _actor(db, token)
        result = [store._decode(r) for r in db.execute('SELECT * FROM encounters ORDER BY created_at,id')]
        reviews = {}
        if actor['role'] in CLINICAL:
            for r in db.execute('SELECT * FROM clinician_reviews ORDER BY id'):
                reviews[r['encounter_id']] = dict(r)
        for r in result:
            r['review'] = reviews.get(r['id'])
            if actor['role'] not in CLINICAL:
                # Explicit projection prevents accidental disclosure via new columns.
                r0 = {k: r[k] for k in ('id','patient_id','patient_name','age','gender','reference',
                       'visit_code','visit_type','created_at','care_status','completed_at')}
                r.clear()
                r.update(r0, classification=None, status='Restricted', symptoms='', review=None,
                         model='', error=None)
        _event(db, actor, 'Patient dashboard viewed', details=dict(record_count=len(result),
               patient_ids=sorted({r['patient_id'] for r in result})))
        return result


def record(token, encounter_id):
    with store._connect() as db:
        actor = _actor(db, token, CLINICAL)
        r = _encounter(db, encounter_id)
        _event(db, actor, 'Patient report viewed', r)
        return r


def register(token, patient, model, reference='', patient_name='', existing_patient_id=None):
    # The internal persistence layer writes the encounter and event in one transaction.
    with store._connect() as db:
        actor = _actor(db, token, ('Reception',)+CLINICAL)
    return store.create_encounter(patient, model, reference, patient_name, existing_patient_id, actor=actor)


def save_ai(token, encounter_id, classification=None, error=None):
    with store._connect() as db:
        actor = _actor(db, token, CLINICAL)
        r = _encounter(db, encounter_id)
        if r['classification']:
            raise ValueError('The saved AI report is retained. Record a staff review separately.')
    store.finish_encounter(encounter_id, classification, error, actor=actor)


def care_status(token, encounter_id, status):
    with store._connect() as db:
        actor = _actor(db, token, CLINICAL)
    store.update_care_status(encounter_id, status, actor=actor)


def patient_name(token, encounter_id, name):
    if len(name) > 120:
        raise ValueError('Patient name must be 120 characters or fewer.')
    with store._connect() as db:
        actor = _actor(db, token, ('Reception',)+CLINICAL)
    store.update_patient_name(encounter_id, name, actor=actor)


def review(token, encounter_id, decision, priority, reason):
    reason = reason.strip()
    if decision not in ('Accept AI suggestion', 'Record clinician decision') or priority not in PRIORITIES or not reason or len(reason)>4000:
        raise ValueError('Choose a decision and priority, and enter a reason (up to 4000 characters).')
    with store._connect() as db:
        actor = _actor(db, token, CLINICAL)
        r = _encounter(db, encounter_id)
        if decision == 'Accept AI suggestion':
            if not r['classification'] or priority != r['classification']['priority']:
                raise ValueError('No matching AI suggestion is available to accept.')
        timestamp = now().isoformat()
        db.execute('''INSERT INTO clinician_reviews
            (encounter_id,actor_id,actor_name,actor_role,created_at,decision,priority,reason)
            VALUES(?,?,?,?,?,?,?,?)''',
            (encounter_id, actor['id'], actor['display_name'], actor['role'], timestamp, decision, priority, reason))
        db.execute('UPDATE encounters SET last_reviewed_at=? WHERE id=?', (timestamp, encounter_id))
        _event(db, actor, 'Clinical review recorded', r, dict(decision=decision, priority=priority, reason=reason))


def set_reminder(token, encounter_id, minutes):
    if minutes is not None and (type(minutes) is not int or not 1<=minutes<=1440):
        raise ValueError('Choose 1-1440 minutes, or disable the reminder.')
    with store._connect() as db:
        actor = _actor(db, token, CLINICAL)
        r = _encounter(db, encounter_id)
        db.execute('UPDATE encounters SET review_interval_minutes=? WHERE id=?', (minutes, encounter_id))
        _event(db, actor, 'Reassessment reminder updated', r,
               dict(before_minutes=r['review_interval_minutes'], after_minutes=minutes))


def observation(token, encounter_id, text, reviewed=False):
    text = text.strip()
    if not text or len(text)>4000:
        raise ValueError('Enter an observation of up to 4000 characters.')
    with store._connect() as db:
        actor = _actor(db, token, CLINICAL)
        r = _encounter(db, encounter_id)
        if reviewed:
            db.execute('UPDATE encounters SET last_reviewed_at=? WHERE id=?', (now().isoformat(), encounter_id))
        _event(db, actor, 'Reassessment recorded' if reviewed else 'Observation recorded', r, dict(note=text))


def due_records(items, at=None):
    at = at or now()
    due = []
    for r in items:
        interval = r.get('review_interval_minutes')
        if interval and r['care_status'] != 'Completed':
            deadline = datetime.fromisoformat(r.get('last_reviewed_at') or r['created_at']) + timedelta(minutes=interval)
            if deadline<=at:
                due.append(dict(r, due_at=deadline.isoformat()))
    return sorted(due, key=lambda r:r['due_at'])


def timeline(token, patient_id):
    with store._connect() as db:
        actor = _actor(db, token, CLINICAL)
        events = [dict(r) for r in db.execute('''SELECT * FROM workflow_events
            WHERE patient_id=? AND action NOT LIKE '%viewed%' ORDER BY occurred_at,id''', (patient_id,))]
        # Older records have no historical event log. Show known saved timestamps honestly.
        for row in db.execute('SELECT * FROM encounters WHERE patient_id=?', (patient_id,)):
            if not any(e['encounter_id']==row['id'] and e['action']=='Patient registered' for e in events):
                events.append(dict(occurred_at=row['created_at'], encounter_id=row['id'], actor_name='Legacy record',
                                   actor_role='Unknown', action='Existing visit', details=json.dumps({'note':'Predates audit logging.'})))
        _event(db, actor, 'Patient timeline viewed', details=dict(patient_id=patient_id))
        return sorted(events, key=lambda r:r['occurred_at'])


def audit(token, limit=250):
    with store._connect() as db:
        actor = _actor(db, token, ('Administrator',))
        result = [dict(r) for r in db.execute('SELECT * FROM workflow_events ORDER BY id DESC LIMIT ?', (limit,))]
        _event(db, actor, 'Audit history viewed')
        return result
