function normalizeSearch(value) {
  return value
    .normalize("NFKD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .replace(/[^\p{Letter}\p{Number}]/gu, "");
}

export function findQuickMatches(players, query) {
  const normalizedQuery = normalizeSearch(query);
  if (!normalizedQuery) return [];
  return players.filter((player) =>
    normalizeSearch(`${player.player_name} ${player.positions.join(" ")}`).includes(normalizedQuery),
  );
}

export function moveQuickSelection(current, direction, count) {
  if (!count) return 0;
  return Math.max(0, Math.min(count - 1, current + direction));
}
