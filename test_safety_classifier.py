import json
import unittest
from unittest.mock import Mock
from safety_classifier import classify_patient, CLASSIFICATION_SCHEMA


class ClassificationTests(unittest.TestCase):
    def setUp(self):
        self.result = dict(priority="Urgent", immediate_emergency=False,
                           concerns=["Reported concern requires assessment"], historical_context=[],
                           reasoning="Review the reported symptoms.", uncertainty="Vitals unknown.")

    def test_full_description_and_selected_model_reach_ollama(self):
        patient = {"age": 42, "gender": "Male", "symptoms": "Feels like an elephant sitting on me; no past episodes"}
        call = Mock(return_value=json.dumps(self.result))
        self.assertEqual(classify_patient(patient, "chosen-model", call), self.result)
        args, kwargs = call.call_args
        self.assertEqual(json.loads(args[0][1]["content"]), patient)
        self.assertEqual(args[1], "chosen-model")
        self.assertEqual(kwargs["response_format"], CLASSIFICATION_SCHEMA)

    def test_invalid_output_is_not_a_negative_screen(self):
        for value in ("not json", "null", "{}", json.dumps(dict(self.result, immediate_emergency="false")),
                      json.dumps(dict(self.result, priority="Safe")),
                      json.dumps(dict(self.result, immediate_emergency=True))):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                classify_patient({}, "model", Mock(return_value=value))

    def test_model_apostrophe_escape_is_normalized(self):
        result = dict(self.result, reasoning="The patient's symptoms need review.")
        raw = json.dumps(result).replace("patient's", "patient" + chr(92) + "'s")
        self.assertEqual(classify_patient({}, "model", Mock(return_value=raw)), result)

    def test_invalid_response_is_corrected_by_model(self):
        call = Mock(side_effect=["{}", json.dumps(self.result)])
        self.assertEqual(classify_patient({}, "model", call), self.result)
        self.assertEqual(call.call_count, 2)
        self.assertIn("Correct your previous response", call.call_args.args[0][-1]["content"])

    def test_inconsistent_emergency_is_reassessed_by_model(self):
        inconsistent = dict(self.result, immediate_emergency=True)
        corrected = dict(inconsistent, priority="Critical")
        call = Mock(side_effect=[json.dumps(inconsistent), json.dumps(corrected)])
        self.assertEqual(classify_patient({}, "model", call), corrected)

    def test_connection_failure_propagates(self):
        with self.assertRaisesRegex(RuntimeError, "offline"):
            classify_patient({}, "model", Mock(side_effect=RuntimeError("offline")))

    def test_history_and_negated_context_are_preserved(self):
        result = dict(self.result, concerns=[], historical_context=["Previous episode; currently denied"])
        self.assertEqual(classify_patient({}, "model", Mock(return_value=json.dumps(result))), result)


if __name__ == "__main__":
    unittest.main()
