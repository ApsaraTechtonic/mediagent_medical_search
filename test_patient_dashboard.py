import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from streamlit.testing.v1 import AppTest
import patient_store as store


def classification(priority, emergency=False):
    return dict(priority=priority, immediate_emergency=emergency, concerns=[], historical_context=[],
                reasoning="Saved explanation for " + priority, uncertainty="Vitals unknown.")


class PatientDashboardTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "records.sqlite3"
        env = patch.dict(os.environ, {"MEDIAGENT_DB_PATH": str(self.path)})
        env.start()
        self.addCleanup(env.stop)

    def add(self, reference, priority=None, emergency=False, failure=None):
        encounter_id = store.create_encounter(dict(age=35, gender="Female", symptoms="Context for " + reference), "test-model", reference)
        if priority:
            store.finish_encounter(encounter_id, classification=classification(priority, emergency))
        elif failure:
            store.finish_encounter(encounter_id, error=failure)
        return encounter_id

    def test_priority_sort_and_separate_uncertain_failed_pending(self):
        self.add("nonurgent", "Non-urgent")
        first = self.add("first urgent", "Urgent")
        second = self.add("second urgent", "Urgent")
        self.add("critical", "Critical")
        self.add("emergency", "Critical", emergency=True)
        self.add("uncertain", "Unable to determine")
        self.add("failed", failure="offline")
        self.add("pending")
        queue, assessment = store.dashboard_groups(store.list_encounters())
        self.assertEqual([r["reference"] for r in queue],
                         ["emergency", "critical", "first urgent", "second urgent", "nonurgent"])
        self.assertEqual([r["reference"] for r in assessment], ["uncertain", "failed", "pending"])
        self.assertNotEqual(first, second)

    def test_distinct_encounters_with_same_reference_and_persistent_reports(self):
        first = self.add("Bed-1", "Urgent")
        second = self.add("Bed-1", "Non-urgent")
        self.assertNotEqual(first, second)
        self.assertTrue(self.path.exists())
        # A new app session reads from disk rather than session_state.
        app = AppTest.from_file("app.py").run()
        with patch("requests.post") as post:
            app.button(key="open_" + first).click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Saved explanation for Urgent" in item.value for item in app.markdown))
            app.button(key="open_" + second).click().run()
            self.assertTrue(any("Saved explanation for Non-urgent" in item.value for item in app.markdown))
            post.assert_not_called()
        self.assertEqual(store.get_encounter(first)["model"], "test-model")

    def test_failed_record_can_be_opened_without_ollama(self):
        encounter_id = self.add("Failed-test", failure="Model offline")
        with patch("requests.post") as post:
            app = AppTest.from_file("app.py").run()
            app.button(key="open_" + encounter_id).click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Model offline" in error.value for error in app.error))
            self.assertTrue(any("Classification unavailable" in warning.value for warning in app.warning))
            post.assert_not_called()

    def test_submission_saves_once_and_can_be_loaded_in_new_session(self):
        response = Mock(status_code=200)
        import json
        response.json.return_value = {"message": {"content": json.dumps(classification("Urgent"))}}
        with patch("requests.post", return_value=response) as post:
            app = AppTest.from_file("app.py").run()
            next(x for x in app.text_input if x.label == "Patient reference (optional)").set_value("DEMO-42")
            app.text_area[0].set_value("Reported patient context")
            next(x for x in app.button if x.label == "Run Triage Analysis").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(post.call_count, 1)
            saved = store.list_encounters()
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["status"], "Complete")
            self.assertEqual(saved[0]["reference"], "DEMO-42")
            app.button(key="refresh_dashboard").click().run()
            self.assertEqual(len(store.list_encounters()), 1)
            self.assertEqual(post.call_count, 1)
        with patch("requests.post") as post:
            fresh = AppTest.from_file("app.py").run()
            fresh.button(key="open_" + saved[0]["id"]).click().run()
            self.assertTrue(any("Saved explanation for Urgent" in x.value for x in fresh.markdown))
            post.assert_not_called()

    def test_model_failure_retains_patient_record(self):
        with patch("requests.post", side_effect=RuntimeError("Model offline")):
            app = AppTest.from_file("app.py").run()
            app.text_area[0].set_value("Reported context")
            next(x for x in app.button if x.label == "Run Triage Analysis").click().run()
            self.assertFalse(app.exception)
        records = store.list_encounters()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["status"], "Failed")
        self.assertEqual(records[0]["error"], "Model offline")

    def test_save_failure_keeps_generated_report_visible(self):
        import json
        import sqlite3
        response = Mock(status_code=200)
        response.json.return_value = {"message": {"content": json.dumps(classification("Urgent"))}}
        with patch("requests.post", return_value=response), patch("patient_store.finish_encounter", side_effect=sqlite3.OperationalError("disk failure")):
            app = AppTest.from_file("app.py").run()
            app.text_area[0].set_value("Reported context")
            next(x for x in app.button if x.label == "Run Triage Analysis").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any("could not be saved" in x.value for x in app.error))
            self.assertTrue(any("Saved explanation for Urgent" in x.value for x in app.markdown))
        self.assertEqual(store.list_encounters()[0]["status"], "Pending")

    def test_storage_unavailable_disables_submission(self):
        import sqlite3
        with patch("patient_store.list_encounters", side_effect=sqlite3.OperationalError("disk failure")), patch("requests.post") as post:
            app = AppTest.from_file("app.py").run()
            self.assertFalse(app.exception)
            submit = next(x for x in app.button if x.label == "Run Triage Analysis")
            self.assertTrue(submit.disabled)
            post.assert_not_called()

    def test_completed_care_retains_report_and_is_searchable(self):
        encounter_id = store.create_encounter(dict(age=35, gender="Female", symptoms="Context"), "model", "Ref-1", "  Demo Asha  ")
        store.finish_encounter(encounter_id, classification=classification("Urgent"))
        before = store.get_encounter(encounter_id)
        self.assertEqual(before["care_status"], "Waiting")
        store.update_care_status(encounter_id, "In care")
        store.update_care_status(encounter_id, "Completed")
        saved = store.get_encounter(encounter_id)
        self.assertEqual(saved["classification"], before["classification"])
        self.assertEqual(saved["symptoms"], before["symptoms"])
        self.assertEqual(saved["status"], "Complete")
        self.assertEqual(saved["care_status"], "Completed")
        self.assertIsNotNone(saved["completed_at"])
        self.assertEqual(store.dashboard_groups(store.list_encounters()), ([], []))
        self.assertEqual(len(store.filter_encounters(store.list_encounters(), "ASHA", "Completed patients")), 1)
        self.assertEqual(store.filter_encounters(store.list_encounters(), "asha", "Active patients"), [])
        store.update_care_status(encounter_id, "Waiting")
        self.assertIsNone(store.get_encounter(encounter_id)["completed_at"])
        self.assertEqual(len(store.dashboard_groups(store.list_encounters())[0]), 1)

    def test_ui_complete_search_reopen_without_model(self):
        encounter_id = self.add("Named-test", "Urgent")
        store.update_patient_name(encounter_id, "Demo Asha")
        with patch("requests.post") as post:
            app = AppTest.from_file("app.py").run()
            app.button(key="open_" + encounter_id).click().run()
            app.button(key="complete_care").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(store.get_encounter(encounter_id)["care_status"], "Completed")
            fresh = AppTest.from_file("app.py").run()
            fresh.text_input(key="patient_search").set_value("ASHA").run()
            fresh.radio(key="patient_view").set_value("Completed patients").run()
            fresh.button(key="open_" + encounter_id).click().run()
            self.assertTrue(any("Saved explanation for Urgent" in x.value for x in fresh.markdown))
            fresh.button(key="reopen_care").click().run()
            self.assertEqual(store.get_encounter(encounter_id)["care_status"], "Waiting")
            self.assertFalse(fresh.exception)
            post.assert_not_called()

    def test_legacy_schema_migration_preserves_original_report(self):
        import sqlite3
        import json
        with sqlite3.connect(self.path) as connection:
            connection.execute("CREATE TABLE encounters (id TEXT PRIMARY KEY, reference TEXT NOT NULL, created_at TEXT NOT NULL, age INTEGER NOT NULL, gender TEXT NOT NULL, symptoms TEXT NOT NULL, model TEXT NOT NULL, status TEXT NOT NULL, classification TEXT, error TEXT)")
            connection.execute("INSERT INTO encounters VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               ("legacy", "Old-ref", "2026-10-28T00:00:00+00:00", 35, "Female", "Old context", "model", "Complete", json.dumps(classification("Urgent")), None))
        connection.close()
        saved = store.get_encounter("legacy")
        self.assertRegex(saved["visit_code"], r"^V[1-9][0-9]*$")
        self.assertIsInstance(saved["patient_id"], int)
        self.assertEqual(saved["id"], "legacy")
        self.assertEqual(saved["patient_name"], "")
        self.assertEqual(saved["care_status"], "Waiting")
        self.assertEqual(saved["classification"], classification("Urgent"))
        store.update_patient_name("legacy", "Demo Legacy")
        self.assertEqual(store.get_encounter("legacy")["patient_name"], "Demo Legacy")
        new_id = self.add("New-ref", "Non-urgent")
        self.assertIsNotNone(store.get_encounter(new_id))
        self.assertEqual(len(store.list_encounters()), 2)

    def test_name_edit_form_and_duplicate_name_encounters(self):
        first = self.add("First-ref", "Urgent")
        second = self.add("Second-ref", "Non-urgent")
        store.update_patient_name(second, "Demo Same")
        with patch("requests.post") as post:
            app = AppTest.from_file("app.py").run()
            app.button(key="open_" + first).click().run()
            app.text_input(key="name_" + first).set_value("Demo Same")
            next(x for x in app.button if x.label == "Save patient name").click().run()
            self.assertFalse(app.exception)
            post.assert_not_called()
        matches = store.filter_encounters(store.list_encounters(), "demo same")
        self.assertEqual({r["id"] for r in matches}, {first, second})
        self.assertEqual(store.filter_encounters(store.list_encounters(), "%"), [])

    def test_running_app_recovers_stale_storage_module(self):
        # Reproduce the screenshot: Python has the earlier module cached in memory.
        del store.filter_encounters
        with patch("requests.post") as post:
            app = AppTest.from_file("app.py").run()
            self.assertFalse(app.exception)
            self.assertTrue(callable(store.filter_encounters))
            post.assert_not_called()

    def test_short_ids_and_return_visits_keep_separate_reports(self):
        first = store.create_encounter(dict(age=35, gender="Female", symptoms="First visit"), "model", patient_name="Demo Asha")
        store.finish_encounter(first, classification=classification("Urgent"))
        original = store.get_encounter(first)
        second = store.create_encounter(dict(age=35, gender="Female", symptoms="Return visit"), "model", patient_name="Demo Asha", existing_patient_id=original["patient_id"])
        returning = store.get_encounter(second)
        self.assertRegex(first, r"^V[1-9][0-9]*$")
        self.assertRegex(store.patient_code(original["patient_id"]), r"^[0-9]{5}$")
        self.assertNotEqual(first, second)
        self.assertEqual(original["patient_id"], returning["patient_id"])
        self.assertEqual(original["visit_type"], "New patient")
        self.assertEqual(returning["visit_type"], "Returning patient")
        self.assertEqual(store.get_encounter(first)["classification"], original["classification"])
        third = store.create_encounter(dict(age=35, gender="Female", symptoms="Different person"), "model", patient_name="Demo Asha")
        self.assertNotEqual(store.get_encounter(third)["patient_id"], original["patient_id"])
        self.assertEqual(len(store.filter_encounters(store.list_encounters(), store.patient_code(original["patient_id"]))), 2)
        self.assertEqual(store.filter_encounters(store.list_encounters(), second), [])
        with self.assertRaises(ValueError):
            store.create_encounter(dict(age=35, gender="Female", symptoms="Context"), "model", existing_patient_id=99999)

    def test_returning_patient_ui_and_history(self):
        import json
        first = self.add("First-visit", "Urgent")
        store.update_patient_name(first, "Demo Asha")
        response = Mock(status_code=200)
        response.json.return_value = {"message": {"content": json.dumps(classification("Non-urgent"))}}
        with patch("requests.post", return_value=response) as post:
            app = AppTest.from_file("app.py").run()
            app.radio(key="registration_type").set_value("Returning patient").run()
            app.text_area[0].set_value("New visit context")
            next(x for x in app.button if x.label == "Run Triage Analysis").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(post.call_count, 1)
            visits = store.list_encounters()
            self.assertEqual(len(visits), 2)
            self.assertEqual(visits[0]["patient_id"], visits[1]["patient_id"])
            self.assertEqual(visits[1]["visit_type"], "Returning patient")
            self.assertTrue(any("Returning patient" in x.value for x in app.caption))
            app.button(key="history_" + first).click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Saved explanation for Urgent" in x.value for x in app.markdown))
            self.assertEqual(post.call_count, 1)

    def test_padded_visit_codes_shorten_without_losing_records(self):
        import sqlite3
        encounter_id = self.add("V000001", "Urgent")
        before = store.get_encounter(encounter_id)
        connection = sqlite3.connect(self.path)
        with connection:
            connection.execute("UPDATE encounters SET visit_code='V000001' WHERE id=?", (encounter_id,))
        connection.close()
        after = store.get_encounter(encounter_id)
        self.assertEqual(after["visit_code"], "V1")
        self.assertEqual(after["reference"], "V1")
        self.assertEqual(after["id"], before["id"])
        self.assertEqual(after["patient_id"], before["patient_id"])
        self.assertEqual(after["classification"], before["classification"])
        self.assertEqual(store.patient_code(after["patient_id"]), "10001")
        new_id = self.add("Custom reference", "Urgent")
        self.assertEqual(new_id, "V2")

    def test_numeric_patient_id_upgrade_preserves_history(self):
        import sqlite3
        first = self.add("Legacy ref", "Urgent")
        before = store.get_encounter(first)
        second = store.create_encounter(dict(age=35, gender="Female", symptoms="Return"), "model", existing_patient_id=before["patient_id"])
        connection = sqlite3.connect(self.path)
        with connection:
            connection.execute("UPDATE patients SET id=1 WHERE id=?", (before["patient_id"],))
            connection.execute("UPDATE encounters SET patient_id=1")
        connection.close()
        upgraded = store.list_encounters()
        self.assertEqual({r["patient_id"] for r in upgraded}, {10001})
        self.assertEqual(store.get_encounter(first)["classification"], before["classification"])
        self.assertEqual(store.get_encounter(second)["visit_type"], "Returning patient")
        self.assertEqual(store.get_encounter(first)["patient_id"], 10001)
        with patch("requests.post") as post:
            app = AppTest.from_file("app.py").run()
            app.button(key="open_" + first).click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any("**Patient ID:** 10001" in x.value for x in app.markdown))
            self.assertFalse(any("Visit ID" in x.value for x in app.markdown))
            self.assertFalse(any(first in x.value or second in x.value for x in app.caption))
            post.assert_not_called()

    def test_unknown_record_update_does_not_silently_succeed(self):
        with self.assertRaises(ValueError):
            store.finish_encounter("not-found", error="Offline")


if __name__ == "__main__":
    unittest.main()
