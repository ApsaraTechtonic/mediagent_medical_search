"""Verify visible warnings even when the model returns no concern strings."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from streamlit.testing.v1 import AppTest


class WarningDisplayTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        env = patch.dict(os.environ, {"MEDIAGENT_DB_PATH": str(Path(folder.name) / "test.sqlite3")})
        env.start()
        self.addCleanup(env.stop)

    def run_case(self, priority, emergency=False):
        result = dict(priority=priority, immediate_emergency=emergency, concerns=[],
                      historical_context=[], reasoning="Context requires review.",
                      uncertainty="Current circumstances are unknown.")
        classification = Mock(status_code=200)
        classification.json.return_value = {"message": {"content": json.dumps(result)}}
        with patch("requests.post", return_value=classification) as post:
            app = AppTest.from_file("app.py").run()
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


if __name__ == "__main__":
    unittest.main()
