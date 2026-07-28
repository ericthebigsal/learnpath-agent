from models import QuizQuestion
from quiz import grade_quiz


def make_quiz():
    return [
        QuizQuestion(question="Q1", options=["a", "b"], correct_index=0),
        QuizQuestion(question="Q2", options=["a", "b"], correct_index=1),
        QuizQuestion(question="Q3", options=["a", "b"], correct_index=0),
        QuizQuestion(question="Q4", options=["a", "b"], correct_index=1),
    ]


def test_grade_quiz_all_correct_scores_100():
    assert grade_quiz(make_quiz(), [0, 1, 0, 1]) == 100.0


def test_grade_quiz_all_wrong_scores_0():
    assert grade_quiz(make_quiz(), [1, 0, 1, 0]) == 0.0


def test_grade_quiz_partial_score_rounds_to_two_decimals():
    # 3 out of 4 correct = 75.0
    assert grade_quiz(make_quiz(), [0, 1, 0, 0]) == 75.0


def test_grade_quiz_empty_quiz_scores_100():
    assert grade_quiz([], []) == 100.0
