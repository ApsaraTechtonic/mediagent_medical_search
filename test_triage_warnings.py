"""Verify visible warnings even when the model returns no concern strings."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from streamlit.testing.v1 import AppTest
import staff_workflow as workflow


class WarningDisplayTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        env = patch.dict(os.environ, {"MEDIAGENT_DB_PATH": str(Path(folder.name) / "test.sqlite3")})
        env.start()
        self.addCleanup(env.stop)
        workflow.bootstrap_admin('admin', 'Admin', 'test-password-123')
        admin = workflow.login('admin', 'test-password-123')
        workflow.create_staff(admin, 'doctor', 'Doctor', 'Doctor', 'test-password-123')
        self.token = workflow.login('doctor', 'test-password-123')

    def run_case(self, priority, emergency=False, concerns=None):
        result = dict(priority=priority, immediate_emergency=emergency, concerns=concerns or [],
                      historical_context=[], reasoning="Context requires review.",
                      uncertainty="Current circumstances are unknown.")
        classification = Mock(status_code=200)
        classification.json.return_value = {"message": {"content": json.dumps(result)}}
        with patch("requests.post", return_value=classification) as post:
            app = AppTest.from_file("app.py")
            app.session_state['staff_token'] = self.token
            app.run()
            app.radio(key='main_navigation').set_value('Register patient').run()
            app.text_area[0].set_value("suicide")
            next(button for button in app.button if button.label == "Run Triage Analysis").click().run(timeout=10)
        self.assertEqual(post.call_count, 1, "A report must require only one successful model call")
        self.assertFalse(app.exception)
        return app

    def test_uncertain_priority_has_warning_with_empty_concerns(self):
        app = self.run_case("Unable to determine")
        self.assertTrue(any("human assessment and clarification required" in x.value for x in app.warning))
        # The alert also persists after an ordinary Streamlit rerun.
        app.run()
        self.assertTrue(any("human assessment and clarification required" in x.value for x in app.warning))

    def test_urgent_priority_has_prominent_warning(self):
        app = self.run_case("Urgent")
        self.assertTrue(any("prompt human assessment required" in x.value for x in app.error))

    def test_emergency_warning_uses_single_model_call(self):
        app = self.run_case("Critical", emergency=True)
        self.assertTrue(any("Possible immediate emergency" in x.value for x in app.error))

    def test_critical_concerns_are_red_on_saved_report_and_rerun(self):
        concern = 'Synthetic critical concern requiring assessment'
        app = self.run_case('Critical', concerns=[concern])
        self.assertTrue(any(x.value==concern for x in app.error))
        self.assertFalse(any(x.value==concern for x in app.warning))
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(any(x.value==concern for x in app.error))
        self.assertTrue(any('prompt human assessment required' in x.value for x in app.error))


if __name__ == "__main__":
    unittest.main()
