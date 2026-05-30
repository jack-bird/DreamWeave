BEGIN;

INSERT INTO users (id, email, nickname)
VALUES ('local_user', NULL, '本地作者')
ON CONFLICT (id) DO UPDATE
SET nickname = EXCLUDED.nickname;

INSERT INTO stories (
  id,
  user_id,
  author_id,
  title,
  description,
  cover_image,
  tags,
  status,
  world_setting,
  character_setting,
  opening_message,
  default_model,
  generation_options
)
VALUES (
  'work_moonlit_inn',
  'local_user',
  'local_user',
  '夜雨客栈',
  '雨夜、旧客栈与失忆旅人交织的低魔悬疑互动故事。',
  '',
  ARRAY['悬疑', '低魔', '古风'],
  'published',
  '群山边境的旧驿道已经荒废多年，夜雨客栈仍在雨幕中亮着灯。这里流传着关于无面账房、失踪镖队和后山禁路的传闻。',
  '玩家是一名在雨夜醒来的旅人，随身只有一枚裂开的玉牌和一封没有署名的旧信。',
  '夜雨落在客栈檐角，灯油在风里轻轻晃动。你在一间陌生客房中醒来，窗外传来马蹄停驻的声音，门缝下缓缓渗进一线冷光。',
  'qwen3:14b',
  '{"num_predict":220,"temperature":0.66,"top_p":0.85,"repeat_penalty":1.08,"think":false}'::jsonb
)
ON CONFLICT (id) DO UPDATE
SET
  author_id = EXCLUDED.author_id,
  title = EXCLUDED.title,
  description = EXCLUDED.description,
  cover_image = EXCLUDED.cover_image,
  tags = EXCLUDED.tags,
  status = EXCLUDED.status,
  world_setting = EXCLUDED.world_setting,
  character_setting = EXCLUDED.character_setting,
  opening_message = EXCLUDED.opening_message,
  default_model = EXCLUDED.default_model,
  generation_options = EXCLUDED.generation_options;

COMMIT;
