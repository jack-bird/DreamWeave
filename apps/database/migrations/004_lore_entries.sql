BEGIN;

CREATE TABLE IF NOT EXISTS lore_entries (
  id text PRIMARY KEY,
  story_id text NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  category text NOT NULL,
  title text NOT NULL,
  keywords text[] NOT NULL DEFAULT '{}',
  content text NOT NULL,
  priority integer NOT NULL DEFAULT 50,
  enabled boolean NOT NULL DEFAULT true,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lore_entries_story
  ON lore_entries(story_id);

CREATE INDEX IF NOT EXISTS idx_lore_entries_category
  ON lore_entries(category);

CREATE INDEX IF NOT EXISTS idx_lore_entries_enabled
  ON lore_entries(enabled);

DROP TRIGGER IF EXISTS trg_lore_entries_set_updated_at ON lore_entries;
CREATE TRIGGER trg_lore_entries_set_updated_at
BEFORE UPDATE ON lore_entries
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMIT;
