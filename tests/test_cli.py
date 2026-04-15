from pathlib import Path
import unittest

from click.testing import CliRunner

from flashcards_cli.main import (
    Card,
    CardProgress,
    RecentMistakesFirstSorter,
    RoundResult,
    SessionStats,
    apply_achievements,
    cli,
    parse_cards_file,
)


class ParseCardsFileTests(unittest.TestCase):
    def test_parses_tab_separated_cards(self):
        cards_file = Path("parse_cards_ok.txt")
        try:
            cards_file.write_text("# comment\ncapital\tulaanbaatar\n2+2\t4\n", encoding="utf-8")
            cards = parse_cards_file(cards_file)
        finally:
            cards_file.unlink(missing_ok=True)

        self.assertEqual(
            cards,
            [Card(question="capital", answer="ulaanbaatar"), Card(question="2+2", answer="4")],
        )

    def test_rejects_invalid_line(self):
        cards_file = Path("parse_cards_bad.txt")
        try:
            cards_file.write_text("missing separator\n", encoding="utf-8")
            with self.assertRaises(Exception) as error:
                parse_cards_file(cards_file)
        finally:
            cards_file.unlink(missing_ok=True)

        self.assertIn("question<TAB>answer", str(error.exception))


class OrganizerTests(unittest.TestCase):
    def test_recent_mistakes_first_keeps_relative_order(self):
        cards = [
            Card(question="q1", answer="a1"),
            Card(question="q2", answer="a2"),
            Card(question="q3", answer="a3"),
        ]
        stats = SessionStats(
            progress={card: CardProgress() for card in cards},
            previous_round_wrong_cards=[cards[1], cards[2]],
        )

        ordered = RecentMistakesFirstSorter().organize(cards, stats)

        self.assertEqual(ordered, [cards[1], cards[2], cards[0]])


class AchievementTests(unittest.TestCase):
    def test_unlocks_new_achievements(self):
        card = Card(question="q1", answer="a1")
        stats = SessionStats(progress={card: CardProgress(correct_answers=3, attempts=6)})
        round_result = RoundResult(all_correct=True, total_answers=2, total_duration=6)

        apply_achievements(stats, round_result, stats.progress)

        self.assertEqual(stats.achievements, {"SPEED", "CORRECT", "REPEAT", "CONFIDENT"})


class CliTests(unittest.TestCase):
    def test_help_exits_without_cards_file(self):
        runner = CliRunner()

        result = runner.invoke(cli, ["--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("recent-", result.output)
        self.assertIn("mistakes-first", result.output)
        self.assertIn("Usage:", result.output)

    def test_cli_runs_with_repetitions_and_inverted_cards(self):
        runner = CliRunner()
        cards_file = Path("cli_cards.txt")
        try:
            cards_file.write_text("capital\tulaanbaatar\n", encoding="utf-8")
            result = runner.invoke(
                cli,
                [str(cards_file), "--repetitions", "3", "--invertCards"],
                input="capital\ncapital\ncapital\n",
            )
        finally:
            cards_file.unlink(missing_ok=True)

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Completed 1 cards.", result.output)
        self.assertIn("CONFIDENT", result.output)


if __name__ == "__main__":
    unittest.main()
