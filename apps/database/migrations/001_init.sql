BEGIN;

CREATE TABLE IF NOT EXISTS users (
  id text PRIMARY KEY,
  email text UNIQUE,
  nickname text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS stories (
  id text PRIMARY KEY,
  user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title text NOT NULL,
  world_setting text NOT NULL DEFAULT '',
  character_setting text NOT NULL DEFAULT '',
  default_model text,
  generation_options jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
  id text PRIMARY KEY,
  user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  story_id text NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  title text NOT NULL DEFAULT '新的会话',
  status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT sessions_status_check CHECK (status IN ('active', 'archived', 'deleted'))
);

CREATE TABLE IF NOT EXISTS ai_tasks (
  id text PRIMARY KEY,
  task_type text NOT NULL DEFAULT 'story_continue',
  status text NOT NULL DEFAULT 'created',
  user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  story_id text NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  session_id text NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  worker_id text,
  request_id text,
  model text,
  input text NOT NULL,
  context jsonb NOT NULL DEFAULT '{}'::jsonb,
  generation_options jsonb NOT NULL DEFAULT '{}'::jsonb,
  output text,
  error_code text,
  error_message text,
  retryable boolean,
  timeout_ms integer,
  duration_ms integer,
  created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  completed_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ai_tasks_task_type_check CHECK (task_type IN ('story_continue', 'story_summary', 'character_reply', 'world_update')),
  CONSTRAINT ai_tasks_status_check CHECK (status IN ('created', 'sent_to_worker', 'running', 'success', 'error', 'timeout', 'cancelled')),
  CONSTRAINT ai_tasks_timeout_ms_check CHECK (timeout_ms IS NULL OR timeout_ms > 0),
  CONSTRAINT ai_tasks_duration_ms_check CHECK (duration_ms IS NULL OR duration_ms >= 0)
);

CREATE TABLE IF NOT EXISTS messages (
  id text PRIMARY KEY,
  session_id text NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  role text NOT NULL,
  content text NOT NULL,
  model text,
  task_id text REFERENCES ai_tasks(id) ON DELETE SET NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT messages_role_check CHECK (role IN ('user', 'assistant', 'system'))
);

CREATE INDEX IF NOT EXISTS idx_stories_user_created
  ON stories(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_sessions_user_updated
  ON sessions(user_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_sessions_story_updated
  ON sessions(story_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_messages_session_created
  ON messages(session_id, created_at ASC, id ASC);

CREATE INDEX IF NOT EXISTS idx_messages_task
  ON messages(task_id);

CREATE INDEX IF NOT EXISTS idx_ai_tasks_session_created
  ON ai_tasks(session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_tasks_status_created
  ON ai_tasks(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_tasks_worker_created
  ON ai_tasks(worker_id, created_at DESC);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_set_updated_at ON users;
CREATE TRIGGER trg_users_set_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_stories_set_updated_at ON stories;
CREATE TRIGGER trg_stories_set_updated_at
BEFORE UPDATE ON stories
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_sessions_set_updated_at ON sessions;
CREATE TRIGGER trg_sessions_set_updated_at
BEFORE UPDATE ON sessions
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_ai_tasks_set_updated_at ON ai_tasks;
CREATE TRIGGER trg_ai_tasks_set_updated_at
BEFORE UPDATE ON ai_tasks
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMIT;
