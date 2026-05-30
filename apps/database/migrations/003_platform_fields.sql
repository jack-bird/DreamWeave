BEGIN;

ALTER TABLE stories
  ADD COLUMN IF NOT EXISTS description text,
  ADD COLUMN IF NOT EXISTS cover_image text,
  ADD COLUMN IF NOT EXISTS tags text[] NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'draft',
  ADD COLUMN IF NOT EXISTS opening_message text,
  ADD COLUMN IF NOT EXISTS author_id text;

UPDATE stories
SET author_id = COALESCE(author_id, user_id)
WHERE author_id IS NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'stories_status_check'
  ) THEN
    ALTER TABLE stories
      ADD CONSTRAINT stories_status_check
      CHECK (status IN ('draft', 'published', 'archived'));
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_stories_status_updated
  ON stories(status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_stories_author_updated
  ON stories(author_id, updated_at DESC);

COMMIT;
