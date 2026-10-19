from dataclasses import dataclass
import random
from typing import Iterable


CORE_POSITIONS = {"PG", "SG", "SF", "PF", "C"}


@dataclass(frozen=True)
class MockCandidate:
    player_id: int
    adp: float | None
    positions: tuple[str, ...]
    positional_scarcity: float
    fantasy_value: float
    decision_score: float | None = None


def _canonical_positions(positions: Iterable[str]) -> set[str]:
    normalized: set[str] = set()
    for position in positions:
        value = position.strip().upper()
        if value == "G":
            normalized.update(("PG", "SG"))
        elif value == "F":
            normalized.update(("SF", "PF"))
        elif value in CORE_POSITIONS:
            normalized.add(value)
    return normalized


def _expand_slots(roster_positions: list[dict]) -> list[str]:
    slots: list[str] = []
    for row in roster_positions:
        position = str(row.get("position") or "").upper()
        try:
            count = max(0, int(float(row.get("count", 0) or 0)))
        except (TypeError, ValueError):
            continue
        slots.extend([position] * count)
    return slots


def _slot_accepts(slot: str, positions: set[str]) -> bool:
    if slot in {"BN", "UTIL", "UT"}:
        return bool(positions)
    if slot == "G":
        return bool(positions & {"PG", "SG"})
    if slot == "F":
        return bool(positions & {"SF", "PF"})
    return slot in positions


def _open_slots(roster_positions: list[dict], drafted_positions: list[set[str]]) -> list[str]:
    slots = _expand_slots(roster_positions)
    assigned: dict[int, int] = {}

    def assign(player_index: int, seen: set[int]) -> bool:
        for slot_index, slot in enumerate(slots):
            if slot_index in seen or not _slot_accepts(slot, drafted_positions[player_index]):
                continue
            seen.add(slot_index)
            previous = assigned.get(slot_index)
            if previous is None or assign(previous, seen):
                assigned[slot_index] = player_index
                return True
        return False

    player_order = sorted(
        range(len(drafted_positions)),
        key=lambda index: sum(
            _slot_accepts(slot, drafted_positions[index]) for slot in slots
        ),
    )
    for player_index in player_order:
        assign(player_index, set())
    return [slot for index, slot in enumerate(slots) if index not in assigned]


def choose_opponent_pick(
    *,
    candidates: list[MockCandidate],
    roster_positions: list[dict],
    drafted_positions: list[set[str]],
    overall_pick: int,
    total_teams: int,
    aggressiveness: float,
    seed: int,
) -> int:
    if not candidates:
        raise ValueError("candidates must not be empty")
    if not 0.0 <= aggressiveness <= 1.0:
        raise ValueError("aggressiveness must be between 0 and 1")
    if overall_pick < 1 or total_teams < 2:
        raise ValueError("draft timing is outside valid bounds")

    open_slots = _open_slots(roster_positions, drafted_positions)
    total_slots = max(len(_expand_slots(roster_positions)), 1)
    known_adp_order = {
        candidate.player_id: index
        for index, candidate in enumerate(sorted(
            (candidate for candidate in candidates if candidate.adp is not None),
            key=lambda candidate: (candidate.adp, -candidate.player_id),
        ))
    }
    utility_order = {
        candidate.player_id: index
        for index, candidate in enumerate(sorted(
            candidates,
            key=lambda candidate: (
                candidate.decision_score
                if candidate.decision_score is not None
                else candidate.fantasy_value,
                candidate.fantasy_value,
                -candidate.player_id,
            ),
            reverse=True,
        ))
    }
    rng = random.Random(f"{seed}:{overall_pick}")
    reach_scale = max(total_teams / 2.0, 1.0)

    def score(candidate: MockCandidate) -> tuple[float, float, int]:
        positions = _canonical_positions(candidate.positions)
        compatible_open = sum(
            _slot_accepts(slot, positions) for slot in open_slots
        )
        positional_demand = compatible_open / total_slots
        scarcity = max(0.0, min(100.0, candidate.positional_scarcity)) / 100.0
        demand_bonus = reach_scale * (0.15 * positional_demand + 0.10 * scarcity)
        noise = rng.uniform(-0.20, 0.20) * reach_scale * aggressiveness
        if candidate.adp is not None:
            market_position = known_adp_order[candidate.player_id]
            market_score = 1.0 - market_position / max(len(known_adp_order), 1)
            pick_distance = max(0.0, candidate.adp - overall_pick) / reach_scale
            market_score += min(pick_distance, 4.0) * aggressiveness / 4.0
        else:
            utility_position = utility_order[candidate.player_id]
            market_score = 1.0 - utility_position / max(len(candidates), 1)
        return (
            market_score + demand_bonus + noise,
            candidate.fantasy_value,
            -candidate.player_id,
        )

    return max(candidates, key=score).player_id


def generate_team_slots(
    *,
    team_keys: list[str],
    manager_team_key: str,
    draft_position: int,
    seed: int,
    advanced_team_slots: dict[str, int] | None = None,
) -> dict[str, int]:
    unique_keys = set(team_keys)
    if len(unique_keys) < 2 or len(unique_keys) != len(team_keys):
        raise ValueError("team_keys must contain at least two unique teams")
    if manager_team_key not in unique_keys:
        raise ValueError("manager team must belong to the imported league")
    if not 1 <= draft_position <= len(unique_keys):
        raise ValueError("draft position is outside the league team count")
    if advanced_team_slots is not None:
        if set(advanced_team_slots) != unique_keys:
            raise ValueError("advanced team slots must map every imported team")
        if sorted(advanced_team_slots.values()) != list(range(1, len(unique_keys) + 1)):
            raise ValueError("advanced team slots must be unique positions from 1 through team count")
        if advanced_team_slots.get(manager_team_key) != draft_position:
            raise ValueError("advanced mapping must keep the manager at the selected draft position")
        return dict(advanced_team_slots)

    opponent_keys = sorted(unique_keys - {manager_team_key})
    opponent_slots = [slot for slot in range(1, len(unique_keys) + 1) if slot != draft_position]
    random.Random(seed).shuffle(opponent_keys)
    return {
        manager_team_key: draft_position,
        **dict(zip(opponent_keys, opponent_slots, strict=True)),
    }
