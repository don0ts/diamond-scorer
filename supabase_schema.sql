-- Diamond Scorer: Supabase (PostgreSQL) Schema
-- Adapted from SQLite schema for PostgreSQL + Supabase RLS

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =========================================
-- CATEGORIES
-- =========================================
CREATE TABLE categories (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    min_age     INTEGER NOT NULL CHECK (min_age >= 0),
    max_age     INTEGER NOT NULL CHECK (max_age >= min_age),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO categories (name, min_age, max_age) VALUES
    ('Toddlers', 4, 5),
    ('Little Kids', 6, 7),
    ('Mini Kids', 8, 9),
    ('Pre Kids', 10, 11),
    ('Kids', 12, 13),
    ('Junior', 14, 16);

-- =========================================
-- TOURNEYS
-- =========================================
CREATE TABLE tourneys (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    abbrev      TEXT,
    category_id BIGINT NOT NULL REFERENCES categories(id),
    is_event    BOOLEAN NOT NULL DEFAULT FALSE,
    year        INTEGER,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =========================================
-- TEAMS
-- =========================================
CREATE TABLE teams (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    abbrev      TEXT,
    place       TEXT,
    category_id BIGINT NOT NULL REFERENCES categories(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =========================================
-- PLAYERS
-- =========================================
CREATE TABLE players (
    id              BIGSERIAL PRIMARY KEY,
    first_name      TEXT NOT NULL,
    middle_name     TEXT,
    last_name       TEXT NOT NULL,
    second_last_name TEXT,
    position        TEXT CHECK (position IN (
        'P', 'C', '1B', '2B', '3B', 'SS',
        'LF', 'CF', 'RF', 'IF', 'OF'
    )),
    bats            TEXT CHECK (bats IN ('L', 'R', 'S')),
    throws          TEXT CHECK (throws IN ('L', 'R')),
    dob             DATE,
    place           TEXT,
    team_id         BIGINT REFERENCES teams(id),
    weight_kg       NUMERIC(5,2) CHECK (weight_kg IS NULL OR weight_kg > 0),
    height_cm       INTEGER CHECK (height_cm IS NULL OR height_cm > 0),
    jersey_number   INTEGER CHECK (jersey_number IS NULL OR jersey_number >= 0),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =========================================
-- TOURNEY_TEAMS
-- =========================================
CREATE TABLE tourney_teams (
    tourney_id  BIGINT NOT NULL REFERENCES tourneys(id) ON DELETE CASCADE,
    team_id     BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    PRIMARY KEY (tourney_id, team_id)
);

-- =========================================
-- GAMES
-- =========================================
CREATE TABLE games (
    id              BIGSERIAL PRIMARY KEY,
    tourney_id      BIGINT NOT NULL REFERENCES tourneys(id),
    away_team_id    BIGINT NOT NULL REFERENCES teams(id),
    home_team_id    BIGINT NOT NULL REFERENCES teams(id),
    game_date       DATE,
    game_time       TIME,
    venue           TEXT,
    innings         INTEGER NOT NULL DEFAULT 9 CHECK (innings > 0),
    away_score      INTEGER NOT NULL DEFAULT 0 CHECK (away_score >= 0),
    home_score      INTEGER NOT NULL DEFAULT 0 CHECK (home_score >= 0),
    status          TEXT NOT NULL DEFAULT 'scheduled'
        CHECK (status IN ('scheduled', 'in_progress', 'finished', 'cancelled', 'postponed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (away_team_id != home_team_id)
);

-- =========================================
-- GAME_LINEUPS
-- =========================================
CREATE TABLE game_lineups (
    id              BIGSERIAL PRIMARY KEY,
    game_id         BIGINT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    side            TEXT NOT NULL CHECK (side IN ('away', 'home')),
    batting_order   INTEGER,
    player_id       BIGINT NOT NULL REFERENCES players(id),
    position        TEXT CHECK (position IN (
        'P', 'C', '1B', '2B', '3B', 'SS',
        'LF', 'CF', 'RF', 'IF', 'OF'
    )),
    is_starter      BOOLEAN NOT NULL DEFAULT TRUE,
    entered_seq     INTEGER,
    sub_for         BIGINT REFERENCES players(id),
    active          BOOLEAN NOT NULL DEFAULT TRUE
);

-- =========================================
-- GAME_EVENTS
-- =========================================
CREATE TABLE game_events (
    id              BIGSERIAL PRIMARY KEY,
    game_id         BIGINT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    seq             INTEGER NOT NULL,
    inning          INTEGER NOT NULL CHECK (inning > 0),
    half            TEXT NOT NULL CHECK (half IN ('top', 'bottom')),
    kind            TEXT NOT NULL CHECK (kind IN ('PA', 'BR', 'SUB')),
    batter_id       BIGINT REFERENCES players(id),
    pitcher_id      BIGINT REFERENCES players(id),
    result          TEXT,
    detail          TEXT,
    bb_type         TEXT CHECK (bb_type IN ('GB', 'LD', 'FB', 'PU')),
    contact         TEXT CHECK (contact IN ('soft', 'avg', 'hard')),
    from_base       INTEGER CHECK (from_base BETWEEN 0 AND 3),
    to_base         INTEGER CHECK (to_base BETWEEN 1 AND 3),
    charged_to      BIGINT REFERENCES players(id),
    credited_to     BIGINT REFERENCES players(id),
    is_error        BOOLEAN NOT NULL DEFAULT FALSE,
    error_on        BIGINT REFERENCES players(id),
    rbi             INTEGER NOT NULL DEFAULT 0,
    outs_recorded   INTEGER NOT NULL DEFAULT 0,
    runs_scored     INTEGER NOT NULL DEFAULT 0,
    advances        JSONB,
    hit_x           REAL CHECK (hit_x IS NULL OR (hit_x >= 0 AND hit_x <= 1)),
    hit_y           REAL CHECK (hit_y IS NULL OR (hit_y >= 0 AND hit_y <= 1)),
    errors_json     JSONB,
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (game_id, seq)
);

-- =========================================
-- GAME_PITCHES
-- =========================================
CREATE TABLE game_pitches (
    id              BIGSERIAL PRIMARY KEY,
    game_id         BIGINT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    event_id        BIGINT REFERENCES game_events(id) ON DELETE SET NULL,
    inning          INTEGER NOT NULL CHECK (inning > 0),
    half            TEXT NOT NULL CHECK (half IN ('top', 'bottom')),
    batter_id       BIGINT REFERENCES players(id),
    pitcher_id      BIGINT REFERENCES players(id),
    pitch_num       INTEGER,
    zone            INTEGER CHECK (zone BETWEEN 1 AND 14),
    velocity        NUMERIC(5,2),
    pitch_type      TEXT CHECK (pitch_type IN ('FF', 'SI', 'FC', 'SL', 'CB', 'CH', 'SP', 'KN')),
    result          TEXT CHECK (result IN ('B', 'CS', 'SS', 'F', 'IP', 'HBP')),
    is_strike       BOOLEAN,
    is_swing        BOOLEAN,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =========================================
-- INDEXES
-- =========================================
CREATE INDEX idx_tourneys_category ON tourneys(category_id);
CREATE INDEX idx_teams_category ON teams(category_id);
CREATE INDEX idx_players_team ON players(team_id);
CREATE INDEX idx_tourney_teams_team ON tourney_teams(team_id);
CREATE INDEX idx_games_tourney ON games(tourney_id);
CREATE INDEX idx_games_away_team ON games(away_team_id);
CREATE INDEX idx_games_home_team ON games(home_team_id);
CREATE INDEX idx_games_date ON games(game_date);
CREATE INDEX idx_games_status ON games(status);
CREATE INDEX idx_game_lineups_game ON game_lineups(game_id);
CREATE INDEX idx_game_lineups_player ON game_lineups(player_id);
CREATE INDEX idx_game_events_game_seq ON game_events(game_id, seq);
CREATE INDEX idx_game_pitches_game ON game_pitches(game_id);
CREATE INDEX idx_game_pitches_event ON game_pitches(event_id);
CREATE INDEX idx_game_pitches_pitcher ON game_pitches(pitcher_id);
CREATE INDEX idx_game_pitches_batter ON game_pitches(batter_id);

-- =========================================
-- UPDATED_AT TRIGGER
-- =========================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_categories_updated_at
    BEFORE UPDATE ON categories
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_tourneys_updated_at
    BEFORE UPDATE ON tourneys
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_teams_updated_at
    BEFORE UPDATE ON teams
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_players_updated_at
    BEFORE UPDATE ON players
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_games_updated_at
    BEFORE UPDATE ON games
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =========================================
-- ROW LEVEL SECURITY (public access, no auth)
-- =========================================
-- Since no auth, enable RLS but allow all operations for anon role
ALTER TABLE categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE tourneys ENABLE ROW LEVEL SECURITY;
ALTER TABLE teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE players ENABLE ROW LEVEL SECURITY;
ALTER TABLE tourney_teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE games ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_lineups ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_pitches ENABLE ROW LEVEL SECURITY;

-- Allow all operations for anon/public access
CREATE POLICY "public_all" ON categories FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "public_all" ON tourneys FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "public_all" ON teams FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "public_all" ON players FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "public_all" ON tourney_teams FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "public_all" ON games FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "public_all" ON game_lineups FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "public_all" ON game_events FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "public_all" ON game_pitches FOR ALL USING (true) WITH CHECK (true);

-- =========================================
-- REALTIME PUBLICATION
-- =========================================
ALTER PUBLICATION supabase_realtime ADD TABLE game_events;
ALTER PUBLICATION supabase_realtime ADD TABLE game_pitches;
ALTER PUBLICATION supabase_realtime ADD TABLE game_lineups;
ALTER PUBLICATION supabase_realtime ADD TABLE games;