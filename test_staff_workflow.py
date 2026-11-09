import os
import json
import sqlite3
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
import patient_store as store
import staff_workflow as wf


class StaffWorkflowTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        env = patch.dict(os.environ, {'MEDIAGENT_DB_PATH':str(Path(folder.name)/'test.sqlite3')})
        env.start()
        self.addCleanup(env.stop)
        wf.bootstrap_admin('admin', 'Admin', 'correct-horse-123')
        self.admin = wf.login('admin', 'correct-horse-123')
        self.tokens = {}
        for role in ('Reception', 'Nurse', 'Doctor'):
            wf.create_staff(self.admin, role, role+' person', role, 'correct-horse-123')
            self.tokens[role] = wf.login(role, 'correct-horse-123')
        self.doctor = self.tokens['Doctor']
        self.patient = dict(age=40, gender='Not specified', symptoms='Fictional test context')

    def add(self, token=None):
        return wf.register(token or self.doctor, self.patient, 'test-model', patient_name='Demo person')

    def app(self, token=None):
        app = AppTest.from_file('app.py', default_timeout=15)
        if token:
            app.session_state['staff_token'] = token
        app.run()
        self.assertFalse(app.exception)
        return app

    def test_login_bootstrap_and_session_revocation(self):
        with self.assertRaises(ValueError):
            wf.bootstrap_admin('other', 'Other', 'correct-horse-123')
        with self.assertRaises(ValueError):
            wf.login('admin', 'incorrect')
        uid = next(r['id'] for r in wf.list_staff(self.admin) if r['role']=='Doctor')
        wf.set_staff_active(self.admin, uid, False)
        with self.assertRaises(PermissionError):
            wf.current_user(self.doctor)
        with self.assertRaises(ValueError):
            wf.login('Doctor', 'correct-horse-123')
        wf.logout(self.tokens['Nurse'])
        with self.assertRaises(PermissionError):
            wf.records(self.tokens['Nurse'])

    def test_selected_login_role_cannot_elevate_permissions(self):
        with self.assertRaises(ValueError):
            wf.login('Reception', 'correct-horse-123', expected_role='Doctor')
        token = wf.login('Reception', 'correct-horse-123', expected_role='Reception')
        self.assertEqual(wf.current_user(token)['role'], 'Reception')
        app = self.app()
        app.radio(key='login_role').set_value('Administrator').run()
        next(t for t in app.text_input if t.label=='Username').set_value('Reception')
        next(t for t in app.text_input if t.label=='Password').set_value('correct-horse-123')
        next(b for b in app.button if b.label=='Sign in').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any('selected sign-in role' in e.value for e in app.error))

    def test_self_signup_needs_approval_and_keeps_user_password(self):
        wf.sign_up('newdoc', 'New doctor', 'Doctor', 'user-chosen-pass')
        account = next(a for a in wf.list_staff(self.admin) if a['username']=='newdoc')
        self.assertEqual(account['approval_state'], 'Pending')
        self.assertEqual(account['active'], 0)
        with self.assertRaisesRegex(ValueError, 'awaiting'):
            wf.login('newdoc', 'user-chosen-pass')
        with self.assertRaises(ValueError):
            wf.sign_up('newadmin', 'Not admin', 'Administrator', 'user-chosen-pass')
        with self.assertRaises(ValueError):
            wf.set_staff_active(self.admin, account['id'], True)
        with self.assertRaises(PermissionError):
            wf.approve_account(self.doctor, account['id'])
        wf.approve_account(self.admin, account['id'])
        token = wf.login('newdoc', 'user-chosen-pass', expected_role='Doctor')
        self.assertEqual(wf.current_user(token)['role'], 'Doctor')
        wf.change_own_password(token, 'user-chosen-pass', 'my-new-password')
        with self.assertRaises(PermissionError):
            wf.current_user(token)
        self.assertTrue(wf.login('newdoc', 'my-new-password'))

    def test_patient_signup_link_and_ui_approval(self):
        eid = self.add()
        wf.sign_up('selfpatient', 'Self patient', 'Patient', 'patient-chosen-pass')
        account = next(a for a in wf.list_staff(self.admin) if a['username']=='selfpatient')
        with self.assertRaises(ValueError):
            wf.approve_account(self.admin, account['id'])
        app = self.app(self.admin)
        app.radio(key='main_navigation').set_value('Patient accounts').run()
        app.radio(key=f"approve_mode_{account['id']}").set_value('Link an existing record').run()
        patient_picker = next(s for s in app.selectbox if s.label == 'Verified patient ID')
        self.assertIsNone(patient_picker.value)
        patient_picker.select(wf.record(self.doctor, eid)['patient_id'])
        next(c for c in app.checkbox if c.label=='I have verified this person and their requested access').check()
        next(b for b in app.button if b.label=='Approve account').click().run()
        self.assertFalse(app.exception)
        token = wf.login('selfpatient', 'patient-chosen-pass')
        self.assertEqual([r['id'] for r in wf.patient_reports(token)], [eid])

    def test_patient_approval_without_registration_and_later_link(self):
        wf.sign_up('newpatient', 'New patient', 'Patient', 'patient-chosen-pass')
        admin = self.app(self.admin)
        admin.radio(key='main_navigation').set_value('Patient accounts').run()
        self.assertFalse(any(s.label == 'Verified patient ID' for s in admin.selectbox))
        next(c for c in admin.checkbox if c.label == 'I have verified this person and their requested access').check()
        next(b for b in admin.button if b.label == 'Approve account').click().run()
        self.assertFalse(admin.exception)

        token = wf.login('newpatient', 'patient-chosen-pass', expected_role='Patient')
        portal = self.app(token)
        self.assertTrue(any('No patient record is linked' in message.value for message in portal.info))
        with self.assertRaises(PermissionError):
            wf.patient_reports(token)

        eid = self.add()
        pid = wf.record(self.doctor, eid)['patient_id']
        admin.radio(key='account_action_Patient accounts').set_value('Manage accounts').run()
        next(s for s in admin.selectbox if s.label == 'Verified patient ID').select(pid)
        next(c for c in admin.checkbox if c.label == 'I have verified this record belongs to this person').check()
        next(b for b in admin.button if b.label == 'Link patient record').click().run()
        self.assertFalse(admin.exception)
        self.assertEqual([r['id'] for r in wf.patient_reports(token)], [eid])

    def test_signup_ui_and_pending_status(self):
        app = self.app()
        app.radio(key='account_access').set_value('Create account').run()
        next(t for t in app.text_input if t.label=='Your name').set_value('New nurse')
        next(t for t in app.text_input if t.label=='Choose a username').set_value('newnurse')
        next(s for s in app.selectbox if s.label=='Requested account role').select('Nurse')
        next(t for t in app.text_input if t.label=='Choose a password (at least 10 characters)').set_value('my-own-password')
        next(t for t in app.text_input if t.label=='Confirm your password').set_value('my-own-password')
        next(b for b in app.button if b.label=='Submit sign-up').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any('Approval is pending' in m.value for m in app.success))
        account = next(a for a in wf.list_staff(self.admin) if a['username']=='newnurse')
        self.assertFalse(account['active'])
        with self.assertRaises(ValueError):
            wf.login('newnurse', 'my-own-password')

    def test_patient_portal_scopes_records_and_denies_staff_actions(self):
        own = self.add()
        other = wf.register(self.doctor, dict(self.patient, symptoms='Other private context'), 'test-model', patient_name='Other person')
        pid = store.get_encounter(own)['patient_id']
        wf.create_patient_account(self.admin, 'patient', 'Demo person', 'patient-pass-123', pid)
        token = wf.login('patient', 'patient-pass-123', expected_role='Patient')
        self.assertEqual([r['id'] for r in wf.patient_reports(token)], [own])
        with self.assertRaises(ValueError):
            wf.patient_reports(token, other)
        with self.assertRaises(PermissionError):
            wf.records(token)
        with self.assertRaises(PermissionError):
            wf.record(token, other)
        with self.assertRaises(PermissionError):
            wf.care_status(token, own, 'Completed')
        with self.assertRaises(PermissionError):
            wf.review(token, own, 'Record clinician decision', 'Urgent', 'Not permitted')
        with self.assertRaises(PermissionError):
            wf.audit(token)
        with self.assertRaises(PermissionError):
            wf.create_patient_account(self.doctor, 'badpatient', 'Other', 'patient-pass-123', pid)
        app = self.app(token)
        self.assertTrue(any('<h1>My patient records</h1>' in x.value for x in app.markdown))
        self.assertFalse(any('Other private context' in x.value for x in app.markdown))
        self.assertFalse(any(b.label=='Run Triage Analysis' for b in app.button))
        wf.logout(token)
        with self.assertRaises(PermissionError):
            wf.patient_reports(token)

    def test_patient_login_routes_to_own_portal(self):
        eid = self.add()
        wf.create_patient_account(self.admin, 'patient', 'Demo person', 'patient-pass-123', store.get_encounter(eid)['patient_id'])
        app = self.app()
        app.radio(key='login_role').set_value('Patient').run()
        next(t for t in app.text_input if t.label=='Username').set_value('patient')
        next(t for t in app.text_input if t.label=='Password').set_value('patient-pass-123')
        next(b for b in app.button if b.label=='Sign in').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any('<h1>My patient records</h1>' in x.value for x in app.markdown))

    def test_patient_can_check_symptoms_and_open_reference_search(self):
        own = self.add()
        patient_id = store.get_encounter(own)['patient_id']
        wf.create_patient_account(self.admin, 'patient', 'Demo person', 'patient-pass-123', patient_id)
        token = wf.login('patient', 'patient-pass-123')
        app = self.app(token)
        navigation = app.radio(key='main_navigation')
        self.assertEqual(navigation.options, [
            'My patient records', 'ER patient triage assistant', 'Medical knowledge search',
        ])
        navigation.set_value('ER patient triage assistant').run()
        next(t for t in app.text_area if t.label == 'Symptoms and relevant context').set_value('Fictional test symptoms')
        classification = dict(priority='Critical', immediate_emergency=True, concerns=[],
                              historical_context=[], reasoning='Test result', uncertainty='Test uncertainty')
        with patch('safety_classifier.classify_patient', return_value=classification) as classifier:
            next(b for b in app.button if b.label == 'Check symptoms').click().run()
        classifier.assert_called_once()
        self.assertFalse(app.exception)
        self.assertTrue(any('Possible immediate emergency' in e.value for e in app.error))
        self.assertEqual([r['id'] for r in wf.records(self.doctor)], [own])
        app.radio(key='main_navigation').set_value('Medical knowledge search').run()
        next(b for b in app.button if b.label == 'Asthma').click().run()
        self.assertEqual(app.text_area(key='knowledge_question').value, 'Asthma')
        self.assertFalse(app.exception)

    def test_admin_can_remove_wrong_patient_link_and_reapprove(self):
        old_visit = self.add()
        new_visit = self.add()
        old_id = store.get_encounter(old_visit)['patient_id']
        new_id = store.get_encounter(new_visit)['patient_id']
        wf.create_patient_account(self.admin, 'patient', 'Demo person', 'patient-pass-123', old_id)
        token = wf.login('patient', 'patient-pass-123')
        account = next(a for a in wf.list_staff(self.admin) if a['username'] == 'patient')
        with self.assertRaises(PermissionError):
            wf.return_patient_account_to_review(self.doctor, account['id'], old_id)
        app = self.app(self.admin)
        app.radio(key='main_navigation').set_value('Patient accounts').run()
        app.radio(key='account_action_Patient accounts').set_value('Manage accounts').run()
        next(b for b in app.button if b.label == 'Remove link and return to review').click().run()
        self.assertFalse(app.exception)
        with self.assertRaises(PermissionError):
            wf.patient_reports(token)
        wf.approve_account(self.admin, account['id'], new_id)
        token = wf.login('patient', 'patient-pass-123')
        self.assertEqual([r['id'] for r in wf.patient_reports(token)], [new_visit])

    def test_reception_and_admin_cannot_access_or_modify_clinical_data(self):
        eid = self.add(self.tokens['Reception'])
        for token in (self.tokens['Reception'], self.admin, 'forged'):
            with self.assertRaises(PermissionError):
                wf.record(token, eid)
            with self.assertRaises(PermissionError):
                wf.review(token, eid, 'Record clinician decision', 'Urgent', 'Test reason')
            with self.assertRaises(PermissionError):
                wf.care_status(token, eid, 'Completed')
            with self.assertRaises(PermissionError):
                wf.observation(token, eid, 'Test observation')
            with self.assertRaises(PermissionError):
                wf.set_reminder(token, eid, 10)
        r = wf.records(self.tokens['Reception'])[0]
        self.assertEqual(r['symptoms'], '')
        self.assertIsNone(r['classification'])
        with self.assertRaises(PermissionError):
            wf.create_staff(self.doctor, 'bad', 'Bad', 'Administrator', 'correct-horse-123')
        with self.assertRaises(PermissionError):
            wf.audit(self.doctor)

    def test_staff_review_preserves_ai_and_sorts_manual_failed_patient(self):
        eid = self.add()
        result = dict(priority='Non-urgent', immediate_emergency=False, concerns=[],
                      historical_context=[], reasoning='Synthetic output', uncertainty='Unknown')
        wf.save_ai(self.doctor, eid, classification=result)
        wf.review(self.doctor, eid, 'Record clinician decision', 'Urgent', 'Staff assessment reason')
        self.assertEqual(store.get_encounter(eid)['classification'], result)
        with self.assertRaises(ValueError):
            wf.save_ai(self.doctor, eid, classification=result)
        failed = self.add()
        wf.save_ai(self.doctor, failed, error='Model offline')
        wf.review(self.tokens['Nurse'], failed, 'Record clinician decision', 'Critical', 'Manual assessment')
        ranked, needs = store.dashboard_groups(wf.records(self.doctor))
        self.assertEqual([r['id'] for r in ranked], [failed, eid])
        self.assertFalse(needs)
        wf.review(self.doctor, eid, 'Accept AI suggestion', 'Non-urgent', 'Accepted after assessment')
        self.assertEqual(wf.records(self.doctor)[0]['review']['priority'], 'Non-urgent')
        self.assertEqual(store.get_encounter(failed)['status'], 'Failed')

    def test_reminders_reset_only_on_assessment_and_stop_when_completed(self):
        eid = self.add()
        self.assertEqual(wf.due_records(wf.records(self.doctor), wf.now()+timedelta(days=2)), [])
        wf.set_reminder(self.doctor, eid, 10)
        future = wf.now()+timedelta(minutes=11)
        self.assertEqual(len(wf.due_records(wf.records(self.doctor), future)), 1)
        with patch('staff_workflow.now', return_value=future):
            wf.observation(self.doctor, eid, 'Reassessed fictional patient', reviewed=True)
        self.assertFalse(wf.due_records(wf.records(self.doctor), future+timedelta(minutes=9)))
        self.assertTrue(wf.due_records(wf.records(self.doctor), future+timedelta(minutes=11)))
        wf.care_status(self.doctor, eid, 'Completed')
        self.assertFalse(wf.due_records(wf.records(self.doctor), future+timedelta(days=3)))
        wf.care_status(self.doctor, eid, 'Waiting')
        self.assertTrue(wf.due_records(wf.records(self.doctor), future+timedelta(days=3)))

    def test_timeline_audit_attribution_and_transaction_rollback(self):
        eid = self.add()
        wf.patient_name(self.tokens['Reception'], eid, 'Updated demo name')
        wf.observation(self.tokens['Nurse'], eid, 'Recorded observation')
        wf.review(self.doctor, eid, 'Record clinician decision', 'Urgent', 'Reason required')
        wf.care_status(self.doctor, eid, 'Completed')
        r = wf.record(self.doctor, eid)
        events = wf.timeline(self.doctor, r['patient_id'])
        self.assertIn('Patient registered', [e['action'] for e in events])
        self.assertIn('Observation recorded', [e['action'] for e in events])
        self.assertIn('Care status changed', [e['action'] for e in events])
        self.assertTrue(any(e['action']=='Patient report viewed' for e in wf.audit(self.admin)))
        with patch('staff_workflow._event', side_effect=RuntimeError('audit failure')):
            with self.assertRaises(RuntimeError):
                wf.care_status(self.doctor, eid, 'Waiting')
        self.assertEqual(store.get_encounter(eid)['care_status'], 'Completed')

    def test_existing_database_migration_preserves_patient_report(self):
        old_path = store.database_path().with_name('legacy.sqlite3')
        result = dict(priority='Urgent', immediate_emergency=False, concerns=[], reasoning='Old report')
        with sqlite3.connect(old_path) as db:
            db.execute('''CREATE TABLE encounters(id TEXT PRIMARY KEY,reference TEXT NOT NULL,
                created_at TEXT NOT NULL,age INTEGER NOT NULL,gender TEXT NOT NULL,symptoms TEXT NOT NULL,
                model TEXT NOT NULL,status TEXT NOT NULL,classification TEXT,error TEXT)''')
            db.execute('INSERT INTO encounters VALUES(?,?,?,?,?,?,?,?,?,?)',
                       ('legacy-id', 'old reference', wf.now().isoformat(), 40, 'Female',
                        'Old context', 'old-model', 'Complete', json.dumps(result), None))
        db.close()
        with patch.dict(os.environ, {'MEDIAGENT_DB_PATH':str(old_path)}):
            wf.initialize()
            wf.initialize()
            saved = store.get_encounter('legacy-id')
            self.assertEqual(saved['classification'], result)
            self.assertEqual(saved['symptoms'], 'Old context')
            self.assertGreaterEqual(saved['patient_id'], 10001)
            self.assertIsNone(saved['review_interval_minutes'])
            self.assertIsNone(saved['last_reviewed_at'])

    def test_sign_in_required_and_admin_screen(self):
        app = self.app()
        self.assertTrue(any(x.label=='Username' for x in app.text_input))
        self.assertFalse(any(x.label=='Run Triage Analysis' for x in app.button))
        app = self.app(self.admin)
        self.assertEqual(app.radio(key='account_action_Staff accounts').value, 'Pending approvals')

    def test_admin_navigation_renders_only_selected_section(self):
        app = self.app(self.admin)
        self.assertEqual(app.radio(key='account_action_Staff accounts').value, 'Pending approvals')
        self.assertFalse(any(c.label=='Show audit history' for c in app.checkbox))
        self.assertFalse(any(b.label=='Refresh dashboard' for b in app.button))
        app.radio(key='main_navigation').set_value('Audit history').run()
        self.assertFalse(app.exception)
        self.assertTrue(any(c.label=='Show audit history' for c in app.checkbox))
        self.assertFalse(any(b.label=='Create staff account' for b in app.button))
        app.radio(key='main_navigation').set_value('Patient dashboard').run()
        self.assertFalse(app.exception)
        self.assertTrue(any(b.label=='Refresh dashboard' for b in app.button))
        self.assertFalse(any(c.label=='Show audit history' for c in app.checkbox))

    def test_knowledge_page_is_separate_from_patient_dashboard(self):
        app = self.app(self.doctor)
        self.assertFalse(any(b.label=='Search Medical Database' for b in app.button))
        app.radio(key='main_navigation').set_value('Medical knowledge search').run()
        self.assertFalse(app.exception)
        self.assertTrue(any(b.label=='Search Medical Database' for b in app.button))
        self.assertFalse(any(b.label=='Refresh dashboard' for b in app.button))

    def test_clinical_screens_are_separate_and_preserve_patient_selection(self):
        first = self.add()
        second = self.add()
        with patch('requests.post') as post:
            app = self.app(self.doctor)
            self.assertFalse(any(b.label=='Run Triage Analysis' for b in app.button))
            self.assertFalse(any(b.label=='Save clinical review' for b in app.button))
            app.button(key='open_'+first).click().run()
            self.assertEqual(app.radio(key='main_navigation').value, 'Patient report')
            self.assertFalse(any(b.label=='Save clinical review' for b in app.button))
            app.radio(key='main_navigation').set_value('Clinical review').run()
            self.assertEqual(app.selectbox(key='visit_selector_Clinical review').value, first)
            self.assertTrue(any(b.label=='Save clinical review' for b in app.button))
            self.assertFalse(any(b.label=='Save observation' for b in app.button))
            app.selectbox(key='visit_selector_Clinical review').select(second).run()
            app.radio(key='main_navigation').set_value('Observations and reminders').run()
            self.assertEqual(app.selectbox(key='visit_selector_Observations and reminders').value, second)
            self.assertTrue(any(b.label=='Save observation' for b in app.button))
            self.assertFalse(any(b.label=='Save clinical review' for b in app.button))
            app.radio(key='main_navigation').set_value('Patient timeline').run()
            self.assertFalse(app.exception)
            self.assertTrue(any(c.label=='Load patient timeline' for c in app.checkbox))
            self.assertFalse(any(b.label=='Save reminder setting' for b in app.button))
            post.assert_not_called()

    def test_ui_observations_reminders_and_completed_retention(self):
        eid = self.add()
        app = self.app(self.doctor)
        app.button(key='open_'+eid).click().run()
        app.radio(key='main_navigation').set_value('Observations and reminders').run()
        next(t for t in app.text_area if t.label=='New observation / recorded vitals').set_value('Fictional observation')
        next(c for c in app.checkbox if c.label=='I reassessed this patient (reset the reminder clock)').check()
        next(b for b in app.button if b.label=='Save observation').click().run()
        self.assertFalse(app.exception)
        self.assertIsNotNone(store.get_encounter(eid)['last_reviewed_at'])
        next(c for c in app.checkbox if c.label=='Enable reassessment reminder').check()
        next(n for n in app.number_input if n.label=='Staff-selected interval in minutes').set_value(1)
        next(b for b in app.button if b.label=='Save reminder setting').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(store.get_encounter(eid)['review_interval_minutes'], 1)
        app.radio(key='main_navigation').set_value('Patient report').run()
        app.button(key='complete_care').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(store.get_encounter(eid)['care_status'], 'Completed')
        self.assertIn('Reassessment recorded', [e['action'] for e in wf.timeline(self.doctor, store.get_encounter(eid)['patient_id'])])

    def test_password_reset_revokes_session_and_keeps_hashes_private(self):
        doctor = next(r for r in wf.list_staff(self.admin) if r['role']=='Doctor')
        self.assertNotIn('password_hash', doctor)
        wf.reset_password(self.admin, doctor['id'], 'replacement-pass-123')
        with self.assertRaises(PermissionError):
            wf.records(self.doctor)
        with self.assertRaises(ValueError):
            wf.login('Doctor', 'correct-horse-123')
        token = wf.login('Doctor', 'replacement-pass-123')
        self.assertEqual(wf.current_user(token)['role'], 'Doctor')
        self.assertNotIn('replacement-pass-123', str(wf.audit(self.admin)))

    def test_ui_manual_registration_review_and_timeline_without_model(self):
        with patch('requests.post') as post:
            app = self.app(self.tokens['Reception'])
            app.radio(key='main_navigation').set_value('Register patient').run()
            app.text_area[0].set_value('Fictional context')
            next(b for b in app.button if b.label=='Register for clinical assessment').click().run()
            self.assertFalse(app.exception)
            eid = store.list_encounters()[0]['id']
            self.assertTrue(app.button(key='open_'+eid).disabled)
            doctor = self.app(self.doctor)
            doctor.button(key='open_'+eid).click().run()
            self.assertFalse(doctor.exception)
            doctor.radio(key='main_navigation').set_value('Clinical review').run()
            next(t for t in doctor.text_area if t.label=='Reason for decision / assessment notes').set_value('Manual assessment for demo')
            next(s for s in doctor.selectbox if s.label=='Staff-assessed priority').select('Urgent')
            next(b for b in doctor.button if b.label=='Save clinical review').click().run()
            self.assertFalse(doctor.exception)
            self.assertEqual(wf.records(self.doctor)[0]['review']['priority'], 'Urgent')
            doctor.radio(key='main_navigation').set_value('Patient timeline').run()
            next(c for c in doctor.checkbox if c.label=='Load patient timeline').check().run()
            self.assertFalse(doctor.exception)
            post.assert_not_called()


if __name__=='__main__':
    unittest.main()
