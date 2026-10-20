"""Pure scoring and pass-rule tests — the boundaries that decide pass/fail."""

import unittest

from server.scoring import is_pass, mastery_level, pass_mark, score_answers


def question(qid, correct, options=("A", "B", "C")):
    return {
        "id": qid,
        "prompt": f"Question {qid}",
        "options": '["A", "B", "C"]',
        "correct": correct,
        "explanation": "Because.",
        "topic": "Topic",
    }


class ScoreTests(unittest.TestCase):
    def test_all_correct_is_100(self):
        score, detail, correct, total = score_answers(
            [question("q1", 0), question("q2", 1)], {"q1": 0, "q2": 1}
        )
        self.assertEqual((score, correct, total), (100, 2, 2))
        self.assertTrue(all(d["is_correct"] for d in detail))

    def test_unanswered_counts_as_wrong(self):
        score, detail, correct, total = score_answers([question("q1", 0)], {})
        self.assertEqual(score, 0)
        self.assertIsNone(detail[0]["chosen"])

    def test_invalid_answer_counts_as_wrong(self):
        score, _, _, _ = score_answers([question("q1", 0)], {"q1": "banana"})
        self.assertEqual(score, 0)

    def test_integer_answer_is_accepted(self):
        score, _, _, _ = score_answers([question("q1", 2)], {"q1": "2"})
        self.assertEqual(score, 100)

    def test_rounding(self):
        score, _, _, _ = score_answers(
            [question("q1", 0), question("q2", 0), question("q3", 0)],
            {"q1": 0, "q2": 1, "q3": 1},
        )
        self.assertEqual(score, 33)

    def test_ten_question_boundaries(self):
        # 7/10 = 70, 8/10 = 80, 9/10 = 90
        for correct, expected in ((7, 70), (8, 80), (9, 90)):
            answers = {f"q{i}": 0 if i < correct else 1 for i in range(10)}
            questions = [question(f"q{i}", 0) for i in range(10)]
            score, _, _, _ = score_answers(questions, answers)
            self.assertEqual(score, expected)


class PassRuleTests(unittest.TestCase):
    def test_quiz_boundary_80(self):
        self.assertFalse(is_pass(79, 80))
        self.assertTrue(is_pass(80, 80))
        self.assertTrue(is_pass(81, 80))

    def test_scenario_boundary_70(self):
        self.assertFalse(is_pass(69, 70))
        self.assertTrue(is_pass(70, 70))

    def test_pass_mark_selection(self):
        settings = {"quiz_pass": 80, "scenario_pass": 70}
        self.assertEqual(pass_mark("quiz", settings), 80)
        self.assertEqual(pass_mark("scenario", settings), 70)


class MasteryTests(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(mastery_level(None), "Not assessed")
        self.assertEqual(mastery_level(0), "Beginner")
        self.assertEqual(mastery_level(49), "Beginner")
        self.assertEqual(mastery_level(50), "Developing")
        self.assertEqual(mastery_level(69), "Developing")
        self.assertEqual(mastery_level(70), "Structured")
        self.assertEqual(mastery_level(84), "Structured")
        self.assertEqual(mastery_level(85), "Optimising")


if __name__ == "__main__":
    unittest.main()
