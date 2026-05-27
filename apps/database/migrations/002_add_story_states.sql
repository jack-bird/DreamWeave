BEGIN;

CREATE TABLE IF NOT EXISTS story_states (
  session_id text PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
  user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  story_id text NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  state jsonb NOT NULL DEFAULT '{}'::jsonb,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_story_states_story
  ON story_states(story_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_story_states_user
  ON story_states(user_id, updated_at DESC);

DROP TRIGGER IF EXISTS trg_story_states_set_updated_at ON story_states;
CREATE TRIGGER trg_story_states_set_updated_at
BEFORE UPDATE ON story_states
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMIT;