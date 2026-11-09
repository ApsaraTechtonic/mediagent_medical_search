import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from streamlit.testing.v1 import AppTest
import patient_store as store
import staff_workflow as wf
from clinical_features import report_markdown
from ui_theme import patient_banner


class TeamAddonTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        env = patch.dict(os.environ, {'MEDIAGENT_DB_PATH':str(Path(folder.name)/'demo.sqlite3')})
        env.start()
        self.addCleanup(env.stop)
        wf.bootstrap_admin('admin', 'Admin', 'test-password-123')
        admin = wf.login('admin', 'test-password-123')
        wf.create_staff(admin, 'doctor', 'Doctor', 'Doctor', 'test-password-123')
        self.token = wf.login('doctor', 'test-password-123')

    def app(self, logged_in=True):
        app = AppTest.from_file('app.py', default_timeout=15)
        if logged_in:
            app.session_state['staff_token'] = self.token
        app.run()
        self.assertFalse(app.exception)
        return app

    def test_richer_intake_is_saved_and_previous_visit_not_overwritten(self):
        with patch('requests.post') as post:
            app = self.app()
            app.radio(key='main_navigation').set_value('Register patient').run()
            next(t for t in app.text_area if t.label=='Symptoms / vitals / relevant context').set_value('Fictional symptoms')
            next(t for t in app.text_input if t.label=='Known allergies and reactions').set_value('Demo allergy')
            next(t for t in app.text_input if t.label=='Blood pressure').set_value('120/80 mmHg')
            next(c for c in app.checkbox if c.label=='Save for manual assessment (skip AI)').check()
            next(b for b in app.button if b.label=='Run Triage Analysis').click().run()
            self.assertFalse(app.exception)
            first = store.list_encounters()[0]
            self.assertEqual(first['intake']['Allergies'], 'Demo allergy')
            self.assertEqual(first['intake']['Blood pressure'], '120/80 mmHg')
            self.assertNotIn('Pain score (0-10)', first['intake'])
            second = wf.register(self.token, dict(age=40, gender='Not specified', symptoms='Return context',
                                 intake={'Current medicines':'Demo medicine'}), 'test', existing_patient_id=first['patient_id'])
            self.assertEqual(store.get_encounter(first['id'])['intake'], first['intake'])
            app.radio(key='main_navigation').set_value('Patient history').run()
            self.assertFalse(app.exception)
            app.button(key='visit_report_'+second).click().run()
            self.assertEqual(app.radio(key='main_navigation').value, 'Patient report')
            self.assertTrue(any('Return context' in m.value for m in app.markdown))
            app.button(key='visit_report_'+first['id']).click().run()
            self.assertTrue(any('Fictional symptoms' in m.value for m in app.markdown))
            self.assertFalse(app.exception)
            post.assert_not_called()

    def test_structured_report_separates_ai_from_staff_and_keeps_unknowns(self):
        eid = wf.register(self.token, dict(age=20, gender='Not specified', symptoms='Demo symptoms'), 'test')
        report = store.get_encounter(eid)
        result = report_markdown(report)
        self.assertIn('No additional intake recorded', result)
        self.assertIn('Unavailable. Continue qualified human assessment.', result)
        result = report_markdown(report, dict(priority='Urgent', reason='Staff reason'))
        self.assertIn('## Staff clinical decision', result)
        self.assertIn('## Original AI suggestion', result)
        self.assertIn('Staff reason', result)

    def test_patient_banner_escapes_text_and_labels_priority_source(self):
        record = dict(patient_name='<script>bad</script>', patient_id=10001, age=28,
                      gender='Not specified', care_status='Waiting', classification={'priority':'Critical'})
        output = patient_banner(record)
        self.assertIn('&lt;script&gt;', output)
        self.assertNotIn('<script>', output)
        self.assertIn('badge-critical', output)
        self.assertIn('AI-suggested priority', output)
        output = patient_banner(record, {'priority':'Urgent'})
        self.assertIn('Staff-assessed priority', output)
        self.assertIn('badge-urgent', output)

    def test_emergency_guide_is_available_without_login_or_model(self):
        with patch('requests.post') as post:
            app = self.app(logged_in=False)
            next(b for b in app.button if b.label=='Open emergency guide').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any(m.value=='112' for m in app.metric))
            self.assertFalse(any(t.label=='Username' for t in app.text_input))
            next(s for s in app.selectbox if s.label=='Your location').select('Outside India / other location').run()
            self.assertFalse(app.metric)
            post.assert_not_called()

    def test_voice_transcript_populates_editable_question_without_search(self):
        with patch('voice_search._voice', return_value={'text':'What is asthma?', 'id':1}), patch('requests.post') as post:
            app = self.app()
            app.radio(key='main_navigation').set_value('Medical knowledge search').run()
            app.checkbox(key='voice_enabled').check().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.text_area(key='knowledge_question').value, 'What is asthma?')
            post.assert_not_called()
            response = Mock(content=b'<nlmSearchResult/>')
            with patch('requests.get', return_value=response) as get:
                app.text_area(key='knowledge_question').set_value('Edited question')
                next(b for b in app.button if b.label=='Search Medical Database').click().run()
                self.assertEqual(app.text_area(key='knowledge_question').value, 'Edited question')
                self.assertTrue(get.called)
            post.assert_not_called()


if __name__=='__main__':
    unittest.main()
