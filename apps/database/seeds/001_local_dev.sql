BEGIN;

INSERT INTO users (id, email, nickname)
VALUES ('user_local', NULL, '本地用户')
ON CONFLICT (id) DO UPDATE
SET nickname = EXCLUDED.nickname;

INSERT INTO stories (
  id,
  user_id,
  title,
  world_setting,
  character_setting,
  default_model,
  generation_options
)
VALUES (
  'story_local',
  'user_local',
  '黑夜古堡',
  '中世纪奇幻世界',
  '用户是失忆的贵族继承人',
  'qwen3:14b',
  '{"num_predict":220,"temperature":0.66,"top_p":0.85,"repeat_penalty":1.08,"think":false}'::jsonb
)
ON CONFLICT (id) DO UPDATE
SET
  title = EXCLUDED.title,
  world_setting = EXCLUDED.world_setting,
  character_setting = EXCLUDED.character_setting,
  default_model = EXCLUDED.default_model,
  generation_options = EXCLUDED.generation_options;

INSERT INTO sessions (id, user_id, story_id, title, status)
VALUES ('session_local', 'user_local', 'story_local', '黑夜古堡：初始会话', 'active')
ON CONFLICT (id) DO UPDATE
SET
  title = EXCLUDED.title,
  status = EXCLUDED.status;

COMMIT;
