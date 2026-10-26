import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { api } from "./api";
import type { League, TeamCategoryBaseline, YahooRosterBaseline } from "./types";

function timestamp(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "unknown";
}

function rosterStatusText(roster: YahooRosterBaseline): string {
  if (roster.roster_data_status === "not_imported") {
    return "Roster not imported; missing data does not mean an empty roster.";
  }
  if (roster.roster_data_status === "stale") {
    return `Snapshot predates a later league/team/settings refresh · Yahoo as of ${timestamp(roster.roster_as_of)}.`;
  }
  return `Yahoo roster snapshot · as of ${timestamp(roster.roster_as_of)}.`;
}

function rosterCountText(roster: YahooRosterBaseline): string {
  if (roster.roster_data_status === "not_imported") return "roster unknown";
  if (roster.roster_data_status === "stale") return `${roster.players.length} in stale snapshot`;
  return `${roster.players.length} rostered`;
}

function categoryValue(
  category: TeamCategoryBaseline["teams"][number]["categories"][number],
): string {
  if (category.raw_value === null) return "Unavailable";
  if (category.calculation_type === "weighted_percentage_from_season_makes_attempts") {
    return `${(category.raw_value * 100).toFixed(1)}%`;
  }
  return category.raw_value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function categoryLabel(label: string): string {
  return label.replaceAll("_", " ");
}

function normalizedPositionText(value: number | null): string {
  return value === null ? "Not available" : `${value.toFixed(0)} / 100`;
}

function categoryComparisonText(
  category: TeamCategoryBaseline["teams"][number]["categories"][number],
): string {
  const relative = category.league_relative;
  if (!relative) return "League-relative comparison unavailable.";
  if (relative.comparison_status === "insufficient") {
    return `Insufficient evidence · ${relative.comparable_team_count} fully covered comparable teams; at least ${relative.minimum_comparable_teams} required.`;
  }
  if (relative.rank === null) {
    return `${relative.comparable_team_count} fully covered comparable teams · this roster is ${relative.coverage_status}; not ranked.`;
  }
  return `Rank ${relative.rank} of ${relative.comparable_team_count} fully covered teams · position ${normalizedPositionText(relative.normalized_position)} · ${categoryLabel(relative.label)}.`;
}

function missingPlayerReason(reason: string): string {
  switch (reason) {
    case "unmapped_nba_identity": return "no NBA identity mapping";
    case "no_stats_for_selected_source": return "no stats for selected source season";
    case "missing_percentage_denominator": return "missing percentage denominator";
    case "missing_percentage_numerator": return "missing percentage numerator";
    case "missing_percentage_numerator_and_denominator": return "missing percentage components";
    default: return reason.replaceAll("_", " ");
  }
}

export function ChampionshipBaseline({ leagues }: { leagues: League[] }) {
  const [leagueKey, setLeagueKey] = useState(leagues[0]?.league_key ?? "");
  const [league, setLeague] = useState<League | null>(null);
  const [rosters, setRosters] = useState<YahooRosterBaseline[] | null>(null);
  const [categoryBaseline, setCategoryBaseline] = useState<TeamCategoryBaseline | null>(null);
  const [identityTeamKey, setIdentityTeamKey] = useState("");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!leagues.some((item) => item.league_key === leagueKey)) {
      setLeagueKey(leagues[0]?.league_key ?? "");
    }
  }, [leagueKey, leagues]);

  useEffect(() => {
    if (!leagueKey) {
      setLeague(null);
      setRosters(null);
      setCategoryBaseline(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError("");
    Promise.all([
      api.getLeague(leagueKey, controller.signal),
      api.getRosters(leagueKey, controller.signal),
      api.getTeamCategoryBaseline(leagueKey, controller.signal),
    ])
      .then(([nextLeague, nextRosters, nextCategoryBaseline]) => {
        setLeague(nextLeague);
        setRosters(nextRosters);
        setCategoryBaseline(nextCategoryBaseline);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : "Could not read the persisted Yahoo baseline.");
          setLeague(null);
          setRosters(null);
          setCategoryBaseline(null);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [leagueKey]);

  useEffect(() => {
    const teams = categoryBaseline?.teams ?? [];
    if (!teams.some((team) => team.team_key === identityTeamKey)) {
      setIdentityTeamKey(teams[0]?.team_key ?? "");
    }
  }, [categoryBaseline, identityTeamKey]);

  async function refreshBaseline() {
    if (!leagueKey) return;
    setBusy(true);
    setError("");
    let importError = "";
    try {
      try {
        await api.importLeagues();
        await api.importPlayers(leagueKey);
      } catch (cause) {
        importError = cause instanceof Error ? cause.message : "Yahoo baseline refresh failed.";
      }
      try {
        const [nextLeague, nextRosters, nextCategoryBaseline] = await Promise.all([
          api.getLeague(leagueKey),
          api.getRosters(leagueKey),
          api.getTeamCategoryBaseline(leagueKey),
        ]);
        setLeague(nextLeague);
        setRosters(nextRosters);
        setCategoryBaseline(nextCategoryBaseline);
        setError(importError);
      } catch (cause) {
        const readError = cause instanceof Error ? cause.message : "Could not reload the persisted Yahoo baseline.";
        setLeague(null);
        setRosters(null);
        setCategoryBaseline(null);
        setError(importError ? `${importError} Saved baseline could not be reloaded: ${readError}` : readError);
      }
    } finally {
      setBusy(false);
    }
  }

  const selectedLeague = leagues.find((item) => item.league_key === leagueKey);
  const identityTeam = categoryBaseline?.teams.find((team) => team.team_key === identityTeamKey);
  return (
    <section className="panel championship-baseline" aria-label="Championship HQ Yahoo baseline">
      <div className="championship-baseline-heading">
        <div>
          <p className="eyebrow">CHAMPIONSHIP HQ · FOUNDATION</p>
          <h2>Yahoo league baseline</h2>
          <p>Persisted league rules and team rosters are the foundation for later roster decisions.</p>
        </div>
        <div className="championship-baseline-controls">
          {leagues.length > 1 && (
            <label className="field">
              <span>Yahoo league</span>
              <select value={leagueKey} onChange={(event) => setLeagueKey(event.target.value)}>
                {leagues.map((item) => (
                  <option key={item.league_key} value={item.league_key}>
                    {item.league_name} · {item.season ?? "season unknown"}
                  </option>
                ))}
              </select>
            </label>
          )}
          <button className="button button-quiet" type="button" onClick={() => void refreshBaseline()}
            disabled={!leagueKey || busy || loading}>
            <RefreshCw size={16} className={busy ? "spin" : ""} />
            {busy ? "Refreshing Yahoo..." : "Refresh Yahoo baseline"}
          </button>
        </div>
      </div>
      {error && <div className="notice notice-error" role="alert">{error}</div>}
      {!leagues.length && <p>No persisted Yahoo league is available yet. Connect Yahoo to establish the baseline.</p>}
      {loading && <p role="status">Loading persisted Yahoo baseline...</p>}
      {league && (
        <>
          <div className="championship-baseline-summary">
            <div>
              <strong>{league.league_name}</strong>
              <span>Season {league.season ?? "unknown"}</span>
            </div>
            <p>League metadata from Yahoo · imported {timestamp(league.league_imported_at)}</p>
            <p>League settings from Yahoo · imported {timestamp(league.settings_imported_at)}</p>
          </div>
          <div className="championship-baseline-settings">
            <section>
              <h3>Scoring rules</h3>
              <p>Yahoo configuration used to interpret future player-value decisions; this baseline does not calculate projections.</p>
              <strong>{league.scoring_settings.scoring_type ?? "Scoring type unavailable"}</strong>
              {league.scoring_settings.categories?.length ? (
                <ul>
                  {league.scoring_settings.categories.map((category) => (
                    <li key={category.stat_id}>
                      {category.name ?? `Yahoo stat ${category.stat_id}`}: {category.value}
                    </li>
                  ))}
                </ul>
              ) : <p>Scoring categories unavailable in persisted Yahoo settings.</p>}
            </section>
            <section>
              <h3>Roster eligibility</h3>
              <p>Yahoo roster slots constrain future start/sit and roster moves; no lineup decision is calculated here.</p>
              {league.roster_positions.length ? (
                <ul>
                  {league.roster_positions.map((slot, index) => (
                    <li key={`${slot.position}-${index}`}>{slot.count} × {slot.position}</li>
                  ))}
                </ul>
              ) : <p>Roster positions unavailable in persisted Yahoo settings.</p>}
            </section>
          </div>
          <section className="team-category-baseline" aria-label="Team category baseline">
            <div className="team-category-baseline-heading">
              <div>
                <h3>Team identity · league-relative</h3>
                <p>Choose a persisted Yahoo team to inspect; manager-team identity is not verified.</p>
              </div>
              {categoryBaseline?.teams.length ? (
                <label className="field team-identity-select">
                  <span>Persisted Yahoo team</span>
                  <select value={identityTeamKey} onChange={(event) => setIdentityTeamKey(event.target.value)}>
                    {categoryBaseline.teams.map((team) => (
                      <option key={team.team_key} value={team.team_key}>
                        {team.team_name ?? team.team_key}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
            </div>
            <p className="team-category-limit">
              A roster baseline, not a projection, league percentile, matchup advantage, recommendation, or championship probability.
            </p>
            <p className="team-category-method">
              {categoryBaseline?.identity_method.calculation_version ?? "Comparison unavailable"}
              {categoryBaseline
                ? ` · requires ${categoryBaseline.identity_method.minimum_comparable_teams} fully covered teams · strength ≥ ${categoryBaseline.identity_method.strength_threshold}, weakness ≤ ${categoryBaseline.identity_method.weakness_threshold} normalized position.`
                : ""}
            </p>
            <p className="team-category-source">
              Selected source season: {categoryBaseline?.selected_source_season ?? "unavailable"}
              {categoryBaseline?.selected_source_stat_type ? ` · ${categoryBaseline.selected_source_stat_type}` : ""}
              {" · "}Latest eligible regular-season stats available among mapped rostered players; players without this season remain missing.
              {" · "}Scoring settings imported {timestamp(categoryBaseline?.settings_imported_at ?? null)}.
            </p>
            <div className="team-identity-content">
              {identityTeam ? (
                <>
                  <div className="team-category-team-heading">
                    <strong>{identityTeam.team_name ?? identityTeam.team_key}</strong>
                    <span>
                      {identityTeam.roster_data_status === "not_imported"
                        ? "Roster not imported; player coverage is unknown."
                        : `${identityTeam.roster_player_count} rostered · ${identityTeam.mapped_player_count} mapped to NBA · ${identityTeam.unmapped_player_count} unmapped · Yahoo as of ${timestamp(identityTeam.roster_as_of)}${identityTeam.roster_data_status === "stale" ? " · stale snapshot" : ""}.`}
                    </span>
                  </div>
                  {identityTeam.categories.length ? identityTeam.categories.map((category) => (
                    <article className="team-category-row" key={category.category_id}>
                      <div className="team-category-value">
                        <strong>{category.category_name ?? `Yahoo stat ${category.category_id}`}</strong>
                        <span>{category.league_relative?.direction === "lower_is_better" ? "lower is better · " : ""}{categoryLabel(category.league_relative?.label ?? "insufficient_evidence")}</span>
                      </div>
                      <p>{category.league_relative?.category_meaning ?? "Configured category; interpretation unavailable."}</p>
                      <p>{categoryComparisonText(category)}</p>
                      <p>
                        Coverage: {category.league_relative?.coverage_status ?? category.status}
                        {" · "}{category.contributing_player_count} category contributors
                        {" · "}{category.missing_or_unmapped_player_count} missing/unmapped.
                        {category.reason ? ` ${category.reason.replaceAll("_", " ")}.` : ""}
                      </p>
                      {category.league_relative?.excluded_teams.length ? (
                        <details className="team-category-exclusions">
                          <summary>Excluded teams ({category.league_relative.excluded_teams.length})</summary>
                          <ul>
                            {category.league_relative.excluded_teams.map((excluded) => (
                              <li key={excluded.team_key}>
                                {excluded.team_name ?? excluded.team_key}: {excluded.coverage_status} · {excluded.reasons.map((reason) => reason.replaceAll("_", " ")).join(", ")}
                              </li>
                            ))}
                          </ul>
                        </details>
                      ) : null}
                      <details className="team-category-raw">
                        <summary>Raw category evidence · {categoryValue(category)}</summary>
                        <p>Status: {category.status}{category.direction === "lower_is_better" ? " · lower is better" : ""} · Calculation: {category.calculation_type ?? "unsupported"}.</p>
                        {category.numerator_total !== null && category.denominator_total !== null && (
                          <p>Weighted season components: {category.numerator_total.toFixed(2)} makes / {category.denominator_total.toFixed(2)} attempts, derived from NBA per-game stats × games played.</p>
                        )}
                        {category.source_imports.map((source) => (
                          <p key={`${source.season}-${source.stat_type}-${source.imported_at}`}>
                            NBA stats {source.season} {source.stat_type} imported {timestamp(source.imported_at)} · {source.player_count_with_source_stats} roster players with source stats, {source.contributing_player_count} category contributors.
                          </p>
                        ))}
                        {category.missing_players.length > 0 && (
                          <ul className="team-category-missing">
                            {category.missing_players.map((player) => (
                              <li key={player.yahoo_player_id}>
                                {player.player_name}: {missingPlayerReason(player.reason)}
                              </li>
                            ))}
                          </ul>
                        )}
                      </details>
                    </article>
                  )) : <p>No configured Yahoo scoring categories are available in persisted settings.</p>}
                </>
              ) : categoryBaseline && categoryBaseline.teams.length === 0 ? (
                <p>No persisted Yahoo teams are available for category evaluation.</p>
              ) : null}
            </div>
          </section>
          <div className="championship-roster-list">
            <h3>Team rosters · Yahoo is authoritative</h3>
            {(rosters ?? []).map((roster) => (
              <details className="championship-roster" key={roster.team_key}>
                <summary>
                  <span>{roster.team_name ?? roster.team_key}</span>
                  <span>{rosterCountText(roster)} · {roster.roster_data_status.replace("_", " ")}</span>
                </summary>
                <p>{rosterStatusText(roster)}</p>
                {roster.players.length ? (
                  <ul>
                    {roster.players.map((player) => (
                      <li key={player.yahoo_player_id}>
                        {player.player_name} · {player.roster_position ?? "Yahoo slot unavailable"}
                      </li>
                    ))}
                  </ul>
                ) : roster.roster_data_status === "available" ? (
                  <p>Yahoo reported no rostered players as of this snapshot.</p>
                ) : null}
              </details>
            ))}
            {rosters && rosters.length === 0 && (
              <p>No Yahoo teams were returned for this persisted league.</p>
            )}
          </div>
          <p className="championship-baseline-limit">
            Matchup and transaction context is not included in this baseline. Snapshot age is shown as an as-of time;
            no age-based freshness cutoff is claimed.
          </p>
        </>
      )}
      {selectedLeague && !league && !loading && !error && (
        <p>League baseline is unavailable until persisted Yahoo data can be read.</p>
      )}
    </section>
  );
}
