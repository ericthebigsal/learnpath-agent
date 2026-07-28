from models import QuizQuestion


def grade_quiz(quiz: list[QuizQuestion], answers: list[int]) -> float:
    if not quiz:
        return 100.0
    correct = sum(
        1 for question, answer in zip(quiz, answers) if answer == question.correct_index
    )
    return round(100 * correct / len(quiz), 2)
