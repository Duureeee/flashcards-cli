from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import random
import time
from abc import ABC, abstractmethod
from typing import Dict, Iterable, List, Sequence, Set, Tuple

import click


SUPPORTED_ORDERS = ("random", "worst-first", "recent-mistakes-first")


@dataclass(frozen=True)
class Card:
    question: str
    answer: str


@dataclass
class CardProgress:
    correct_answers: int = 0
    attempts: int = 0
    mistakes: int = 0


@dataclass
class RoundResult:
    all_correct: bool = True
    total_answers: int = 0
    total_duration: float = 0.0


@dataclass
class SessionStats:
    progress: Dict[Card, CardProgress] = field(default_factory=dict)
    previous_round_wrong_cards: List[Card] = field(default_factory=list)
    achievements: Set[str] = field(default_factory=set)


class CardOrganizer(ABC):
    @abstractmethod
    def organize(self, cards: Sequence[Card], stats: SessionStats) -> List[Card]:
        raise NotImplementedError


class RandomCardOrganizer(CardOrganizer):
    def organize(self, cards: Sequence[Card], stats: SessionStats) -> List[Card]:
        ordered = list(cards)
        random.shuffle(ordered)
        return ordered


class WorstFirstOrganizer(CardOrganizer):
    def organize(self, cards: Sequence[Card], stats: SessionStats) -> List[Card]:
        def sort_key(card: Card) -> Tuple[int, int]:
            progress = stats.progress.get(card, CardProgress())
            return (-progress.mistakes, progress.attempts)

        return sorted(cards, key=sort_key)


class RecentMistakesFirstSorter(CardOrganizer):
    def organize(self, cards: Sequence[Card], stats: SessionStats) -> List[Card]:
        wrong_cards = list(stats.previous_round_wrong_cards)
        wrong_set = set(wrong_cards)
        return wrong_cards + [card for card in cards if card not in wrong_set]


def get_organizer(name: str) -> CardOrganizer:
    organizers = {
        "random": RandomCardOrganizer(),
        "worst-first": WorstFirstOrganizer(),
        "recent-mistakes-first": RecentMistakesFirstSorter(),
    }
    return organizers[name]


def parse_cards_file(cards_file: Path) -> List[Card]:
    if not cards_file.exists():
        raise click.ClickException(f"Cards file not found: {cards_file}")

    cards: List[Card] = []
    for line_number, raw_line in enumerate(cards_file.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "\t" not in line:
            raise click.ClickException(
                "Invalid cards file format. Use one card per line as "
                "'question<TAB>answer'."
                f" Error at line {line_number}."
            )
        question, answer = [part.strip() for part in line.split("\t", 1)]
        if not question or not answer:
            raise click.ClickException(
                f"Invalid card at line {line_number}. Question and answer are required."
            )
        cards.append(Card(question=question, answer=answer))

    if not cards:
        raise click.ClickException("Cards file is empty.")
    return cards


def ask_card(card: Card, invert_cards: bool) -> Tuple[bool, float]:
    prompt_text = card.answer if invert_cards else card.question
    expected = card.question if invert_cards else card.answer
    started_at = time.perf_counter()
    user_answer = click.prompt(prompt_text, prompt_suffix=" -> ", type=str)
    duration = time.perf_counter() - started_at
    return user_answer.strip() == expected, duration


def apply_achievements(
    stats: SessionStats, round_result: RoundResult, progress_for_round: Dict[Card, CardProgress]
) -> None:
    if round_result.total_answers and round_result.total_duration / round_result.total_answers < 5:
        stats.achievements.add("SPEED")
    if round_result.total_answers and round_result.all_correct:
        stats.achievements.add("CORRECT")
    if any(progress.attempts > 5 for progress in progress_for_round.values()):
        stats.achievements.add("REPEAT")
    if any(progress.correct_answers >= 3 for progress in progress_for_round.values()):
        stats.achievements.add("CONFIDENT")


def study_cards(
    cards: Sequence[Card], order: str, repetitions: int, invert_cards: bool
) -> SessionStats:
    organizer = get_organizer(order)
    stats = SessionStats(progress={card: CardProgress() for card in cards})
    remaining = {card for card in cards}

    while remaining:
        ordered_cards = organizer.organize(list(remaining), stats)
        round_result = RoundResult()
        wrong_cards: List[Card] = []

        for card in ordered_cards:
            correct, duration = ask_card(card, invert_cards)
            progress = stats.progress[card]
            progress.attempts += 1
            round_result.total_answers += 1
            round_result.total_duration += duration

            if correct:
                progress.correct_answers += 1
                click.echo("Correct!")
                if progress.correct_answers >= repetitions:
                    remaining.discard(card)
            else:
                progress.mistakes += 1
                progress.correct_answers = 0
                round_result.all_correct = False
                wrong_cards.append(card)
                expected = card.question if invert_cards else card.answer
                click.echo(f"Wrong! Correct answer: {expected}")

        apply_achievements(stats, round_result, stats.progress)
        stats.previous_round_wrong_cards = wrong_cards

    return stats


def validate_order(ctx: click.Context, param: click.Parameter, value: str) -> str:
    if value not in SUPPORTED_ORDERS:
        supported = ", ".join(SUPPORTED_ORDERS)
        raise click.BadParameter(f"unsupported order '{value}'. Choose one of: {supported}")
    return value


@click.command(context_settings={"help_option_names": ["--help"]})
@click.argument("cards_file", required=False, type=click.Path(path_type=Path))
@click.option(
    "--order",
    default="random",
    show_default=True,
    callback=validate_order,
    help='Card order: "random", "worst-first", or "recent-mistakes-first".',
)
@click.option(
    "--repetitions",
    default=1,
    type=click.IntRange(1),
    show_default=True,
    help="Required number of consecutive correct answers before a card is completed.",
)
@click.option(
    "--invertCards",
    is_flag=True,
    default=False,
    help="Swap question and answer when asking cards.",
)
def cli(cards_file: Path | None, order: str, repetitions: int, invertcards: bool) -> None:
    if cards_file is None:
        raise click.UsageError("Missing argument 'CARDS_FILE'. Use --help for usage details.")

    cards = parse_cards_file(cards_file)
    stats = study_cards(cards, order=order, repetitions=repetitions, invert_cards=invertcards)
    achievements = ", ".join(sorted(stats.achievements)) if stats.achievements else "None"
    click.echo(f"Completed {len(cards)} cards.")
    click.echo(f"Achievements: {achievements}")


def main(argv: Iterable[str] | None = None) -> None:
    args = list(argv) if argv is not None else None
    cli.main(args=args, prog_name="flashcard", standalone_mode=True)
