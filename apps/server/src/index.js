"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { URL } = require("node:url");

loadEnvFiles();

const WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
const HOST = process.env.DREAMWEAVE_SERVER_HOST || "127.0.0.1";
const PORT = Number(process.env.DREAMWEAVE_SERVER_PORT || 3000);
const WORKER_PATH = process.env.DREAMWEAVE_WORKER_PATH || "/ws/worker";
const SERVER_TASK_TIMEOUT = Number(process.env.DREAMWEAVE_SERVER_TASK_TIMEOUT || 200000);
const HEARTBEAT_INTERVAL = Number(process.env.DREAMWEAVE_HEARTBEAT_INTERVAL || 15000);
const WORKER_OFFLINE_TIMEOUT = Number(process.env.DREAMWEAVE_WORKER_OFFLINE_TIMEOUT || 45000);
const DATABASE_URL = process.env.DATABASE_URL || "";

const workers = new Map();
const pendingTasks = new Map();
const MOBILE_WEB_DIR = path.resolve(__dirname, "..", "..", "mobile-web");
const CONTENT_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
};

const database = createDatabase();

function loadEnvFiles() {
  const candidates = [
    process.env.DREAMWEAVE_ENV_FILE,
    path.resolve(process.cwd(), ".env"),
    path.resolve(__dirname, "..", "..", "..", ".env"),
    path.resolve(__dirname, "..", "..", "..", "..", ".env"),
    "/opt/dreamweave/.env",
  ].filter(Boolean);

  const loaded = new Set();
  for (const filePath of candidates) {
    if (loaded.has(filePath) || !fs.existsSync(filePath)) {
      continue;
    }

    loaded.add(filePath);
    const content = fs.readFileSync(filePath, "utf8");
    for (const rawLine of content.split(/\r?\n/)) {
      const line = rawLine.trim();
      if (!line || line.startsWith("#")) {
        continue;
      }

      const match = line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
      if (!match || process.env[match[1]] !== undefined) {
        continue;
      }

      process.env[match[1]] = unquoteEnvValue(match[2].trim());
    }
  }
}

function unquoteEnvValue(value) {
  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    return value.slice(1, -1);
  }
  return value;
}

function createDatabase() {
  if (!DATABASE_URL) {
    return {
      pool: null,
      configured: false,
      error: null,
    };
  }

  try {
    const { Pool } = require("pg");
    return {
      pool: new Pool({
        connectionString: DATABASE_URL,
        max: Number(process.env.DREAMWEAVE_DB_POOL_SIZE || 5),
        idleTimeoutMillis: 30000,
      }),
      configured: true,
      error: null,
    };
  } catch (error) {
    console.warn(`[server] PostgreSQL disabled: ${error.message}`);
    return {
      pool: null,
      configured: true,
      error: error.message,
    };
  }
}

function nowIso() {
  return new Date().toISOString();
}

function makeId(prefix) {
  return `${prefix}_${crypto.randomUUID().replaceAll("-", "")}`;
}

function makeMessage(type, payload, requestId = makeId("req")) {
  return {
    type,
    request_id: requestId,
    timestamp: nowIso(),
    payload,
  };
}

async function databaseStatus() {
  const status = {
    configured: database.configured,
    connected: Boolean(database.pool),
    error: database.error || undefined,
  };

  if (!database.pool) {
    return status;
  }

  try {
    await database.pool.query("SELECT 1");
    return {
      configured: true,
      connected: true,
    };
  } catch (error) {
    return {
      configured: true,
      connected: false,
      error: error.message,
    };
  }
}

async function handleHealth(req, res) {
  sendJson(res, 200, {
    status: "ok",
    server_time: nowIso(),
    database: await databaseStatus(),
    worker_count: getConnectedWorkers().length,
    pending_task_count: pendingTasks.size,
    workers: getConnectedWorkers().map(publicWorker),
  });
}

async function withDbTransaction(callback) {
  if (!database.pool) {
    return null;
  }

  const client = await database.pool.connect();
  try {
    await client.query("BEGIN");
    const result = await callback(client);
    await client.query("COMMIT");
    return result;
  } catch (error) {
    try {
      await client.query("ROLLBACK");
    } catch (rollbackError) {
      console.warn(`[server] Database rollback failed: ${rollbackError.message}`);
    }
    throw error;
  } finally {
    client.release();
  }
}

function jsonParam(value) {
  return JSON.stringify(value || {});
}

function cleanText(value, fallback = "") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function userNickname(userId) {
  if (userId === "local_user" || userId === "user_local") {
    return "本地用户";
  }
  return userId || "用户";
}

function requireDatabase(res) {
  if (database.pool) {
    return true;
  }

  sendJson(res, 503, {
    status: "error",
    error_code: "DATABASE_UNAVAILABLE",
    message: database.configured
      ? database.error || "PostgreSQL is configured but unavailable"
      : "PostgreSQL is not configured",
  });
  return false;
}

async function ensureUser(client, userId) {
  await client.query(
    `
    INSERT INTO users (id, nickname)
    VALUES ($1, $2)
    ON CONFLICT (id) DO UPDATE
    SET nickname = EXCLUDED.nickname
    `,
    [userId, userNickname(userId)],
  );
}

async function persistTaskDispatch(task, worker, requestId, timeoutMs) {
  if (!database.pool) {
    if (database.configured) {
      throw new Error(database.error || "PostgreSQL is configured but unavailable");
    }
    return;
  }

  const context = task.context || {};
  const storyTitle = cleanText(context.story_title, "黑夜古堡");
  const worldSetting = cleanText(context.world_setting, "中世纪奇幻世界");
  const characterSetting = cleanText(context.character_setting, "用户是失忆的贵族继承人");
  const sessionTitle = storyTitle ? `${storyTitle}：当前会话` : "新的会话";
  const now = new Date();

  await withDbTransaction(async (client) => {
    await client.query(
      `
      INSERT INTO users (id, nickname)
      VALUES ($1, $2)
      ON CONFLICT (id) DO UPDATE
      SET nickname = EXCLUDED.nickname
      `,
      [task.user_id, userNickname(task.user_id)],
    );

    await client.query(
      `
      INSERT INTO stories (
        id,
        user_id,
        title,
        world_setting,
        character_setting,
        default_model,
        generation_options
      )
      VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
      ON CONFLICT (id) DO UPDATE
      SET
        title = EXCLUDED.title,
        world_setting = EXCLUDED.world_setting,
        character_setting = EXCLUDED.character_setting,
        default_model = EXCLUDED.default_model,
        generation_options = EXCLUDED.generation_options
      `,
      [
        task.story_id,
        task.user_id,
        storyTitle,
        worldSetting,
        characterSetting,
        task.model || null,
        jsonParam(task.generation_options),
      ],
    );

    await client.query(
      `
      INSERT INTO sessions (id, user_id, story_id, title, status)
      VALUES ($1, $2, $3, $4, 'active')
      ON CONFLICT (id) DO UPDATE
      SET
        story_id = EXCLUDED.story_id,
        title = EXCLUDED.title,
        status = 'active'
      `,
      [task.session_id, task.user_id, task.story_id, sessionTitle],
    );

    await client.query(
      `
      INSERT INTO ai_tasks (
        id,
        task_type,
        status,
        user_id,
        story_id,
        session_id,
        worker_id,
        request_id,
        model,
        input,
        context,
        generation_options,
        timeout_ms,
        started_at
      )
      VALUES ($1, $2, 'sent_to_worker', $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11::jsonb, $12, $13)
      ON CONFLICT (id) DO UPDATE
      SET
        status = EXCLUDED.status,
        worker_id = EXCLUDED.worker_id,
        request_id = EXCLUDED.request_id,
        model = EXCLUDED.model,
        input = EXCLUDED.input,
        context = EXCLUDED.context,
        generation_options = EXCLUDED.generation_options,
        timeout_ms = EXCLUDED.timeout_ms,
        started_at = EXCLUDED.started_at
      `,
      [
        task.task_id,
        task.task_type,
        task.user_id,
        task.story_id,
        task.session_id,
        worker.workerId,
        requestId,
        task.model || null,
        task.input,
        jsonParam(task.context),
        jsonParam(task.generation_options),
        timeoutMs,
        now,
      ],
    );

    await client.query(
      `
      INSERT INTO messages (id, session_id, role, content, task_id, metadata)
      VALUES ($1, $2, 'user', $3, $4, $5::jsonb)
      `,
      [
        makeId("msg"),
        task.session_id,
        task.input,
        task.task_id,
        jsonParam({
          request_id: requestId,
          story_id: task.story_id,
        }),
      ],
    );
  });
}

async function persistTaskSuccess(pending, message, responsePayload) {
  if (!database.pool) {
    return;
  }

  const task = pending.task;
  const payload = message.payload || {};
  const content = cleanText(payload.content, "");
  const model = payload.model || task.model || null;
  const durationMs = Number(payload.duration_ms || Date.now() - pending.startedAt);
  const stateUpdate = payload.state_update || null;

  await withDbTransaction(async (client) => {
    await client.query(
      `
      UPDATE ai_tasks
      SET
        status = 'success',
        output = $2,
        model = COALESCE($3, model),
        worker_id = $4,
        duration_ms = $5,
        completed_at = now()
      WHERE id = $1
      `,
      [task.task_id, content, model, payload.worker_id || pending.workerId, durationMs],
    );

    await client.query(
      `
      INSERT INTO messages (id, session_id, role, content, model, task_id, metadata)
      VALUES ($1, $2, 'assistant', $3, $4, $5, $6::jsonb)
      `,
      [
        makeId("msg"),
        task.session_id,
        content,
        model,
        task.task_id,
        jsonParam({
          request_id: responsePayload.request_id,
          worker_id: payload.worker_id || pending.workerId,
          usage: payload.usage || null,
          agent_trace: payload.agent_trace || null,
        }),
      ],
    );

    if (stateUpdate && typeof stateUpdate === 'object') {
      await upsertStoryState(client, task.session_id, task.user_id, task.story_id, stateUpdate);
    }

    await client.query("UPDATE sessions SET updated_at = now() WHERE id = $1", [task.session_id]);
  });
}

async function persistTaskError(pending, payload, status = "error") {
  if (!database.pool || !pending?.task) {
    return;
  }

  const durationMs = Math.max(Date.now() - pending.startedAt, 0);
  const errorMessage = formatTaskErrorMessage(payload);
  await withDbTransaction(async (client) => {
    await client.query(
      `
      UPDATE ai_tasks
      SET
        status = $2,
        error_code = $3,
        error_message = $4,
        retryable = $5,
        duration_ms = $6,
        completed_at = now()
      WHERE id = $1
      `,
      [
        pending.task.task_id,
        status,
        payload.error_code || "UNKNOWN_ERROR",
        errorMessage,
        payload.retryable ?? null,
        durationMs,
      ],
    );

    await client.query("UPDATE sessions SET updated_at = now() WHERE id = $1", [pending.task.session_id]);
  });
}

function formatTaskErrorMessage(payload) {
  const baseMessage = cleanText(payload.message, "");
  const detail = payload.detail && typeof payload.detail === "object" ? payload.detail : {};
  const qualityIssues = Array.isArray(detail.quality_issues) ? detail.quality_issues : [];

  if (qualityIssues.length) {
    const issueText = qualityIssues.map((issue) => String(issue)).join("; ");
    return baseMessage ? `${baseMessage} | quality_issues=${issueText}` : `quality_issues=${issueText}`;
  }

  return baseMessage || null;
}

async function handleSessionMessages(req, res, sessionId) {
  if (!database.pool) {
    sendJson(res, 200, {
      session_id: sessionId,
      persistence_enabled: false,
      messages: [],
    });
    return;
  }

  try {
    const result = await database.pool.query(
      `
      SELECT id, role, content, model, task_id, metadata, created_at
      FROM messages
      WHERE session_id = $1
      ORDER BY created_at ASC, id ASC
      LIMIT 200
      `,
      [sessionId],
    );

    sendJson(res, 200, {
      session_id: sessionId,
      persistence_enabled: true,
      messages: result.rows.map((row) => ({
        id: row.id,
        role: row.role,
        content: row.content,
        model: row.model,
        task_id: row.task_id,
        metadata: row.metadata,
        created_at: row.created_at,
      })),
    });
  } catch (error) {
    sendJson(res, 500, {
      status: "error",
      error_code: "DB_READ_FAILED",
      message: error.message,
    });
  }
}

async function getStoryState(sessionId) {
  if (!database.pool) {
    return null;
  }

  try {
    const result = await database.pool.query(
      `
      SELECT state, version, created_at, updated_at
      FROM story_states
      WHERE session_id = $1
      `,
      [sessionId],
    );

    if (result.rows.length === 0) {
      return null;
    }

    return {
      session_id: sessionId,
      state: result.rows[0].state,
      version: result.rows[0].version,
      created_at: result.rows[0].created_at,
      updated_at: result.rows[0].updated_at,
    };
  } catch (error) {
    console.error(`[server] Failed to get story state for session ${sessionId}:`, error);
    return null;
  }
}

async function updateStoryState(sessionId, userId, storyId, stateUpdate) {
  if (!database.pool) {
    return null;
  }

  try {
    return await withDbTransaction(async (client) => {
      return await upsertStoryState(client, sessionId, userId, storyId, stateUpdate);
    });
  } catch (error) {
    console.error(`[server] Failed to update story state for session ${sessionId}:`, error);
    return null;
  }
}

async function upsertStoryState(client, sessionId, userId, storyId, stateUpdate) {
  const existingResult = await client.query(
    `
    SELECT state, version
    FROM story_states
    WHERE session_id = $1
    FOR UPDATE
    `,
    [sessionId],
  );

  const sanitizedUpdate = sanitizeStoryStateUpdate(stateUpdate);
  let newState;
  let newVersion;

  if (existingResult.rows.length === 0) {
    newState = sanitizedUpdate;
    newVersion = 1;

    await client.query(
      `
      INSERT INTO story_states (session_id, user_id, story_id, state, version)
      VALUES ($1, $2, $3, $4::jsonb, $5)
      `,
      [sessionId, userId, storyId, JSON.stringify(newState), newVersion],
    );
  } else {
    const existingState = existingResult.rows[0].state || {};
    const existingVersion = existingResult.rows[0].version;
    newState = mergeStoryState(existingState, sanitizedUpdate);
    newVersion = existingVersion + 1;

    await client.query(
      `
      UPDATE story_states
      SET state = $2::jsonb, version = $3, updated_at = now()
      WHERE session_id = $1
      `,
      [sessionId, JSON.stringify(newState), newVersion],
    );
  }

  return {
    session_id: sessionId,
    state: newState,
    version: newVersion,
  };
}

function sanitizeStoryStateUpdate(update) {
  const allowedKeys = new Set([
    "current_world",
    "current_scene",
    "story_stage",
    "long_summary",
    "characters",
    "relationships",
    "world_flags",
    "inventory",
    "pending_events",
  ]);
  const sanitized = {};

  for (const [key, value] of Object.entries(update || {})) {
    if (allowedKeys.has(key) && value !== undefined && value !== null) {
      sanitized[key] = value;
    }
  }

  return sanitized;
}

function mergeStoryState(target, source) {
  const result = mergeDeep(target || {}, source || {});

  if (Array.isArray(target?.pending_events) || Array.isArray(source?.pending_events)) {
    result.pending_events = mergeUniqueStrings(target?.pending_events, source?.pending_events, 10);
  }

  if (Array.isArray(target?.inventory) || Array.isArray(source?.inventory)) {
    result.inventory = mergeUniqueValues(target?.inventory, source?.inventory, 50);
  }

  if (typeof source?.long_summary === "string") {
    result.long_summary = source.long_summary.slice(-1200);
  }

  return result;
}

function mergeDeep(target, source) {
  const result = { ...target };

  for (const key in source || {}) {
    if (isPlainObject(source[key])) {
      result[key] = mergeDeep(isPlainObject(result[key]) ? result[key] : {}, source[key]);
    } else {
      result[key] = source[key];
    }
  }

  return result;
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function mergeUniqueStrings(left, right, limit) {
  const values = [...(left || []), ...(right || [])]
    .filter((value) => typeof value === "string" && value.trim())
    .map((value) => value.trim());
  return [...new Set(values)].slice(-limit);
}

function mergeUniqueValues(left, right, limit) {
  const seen = new Set();
  const result = [];

  for (const item of [...(left || []), ...(right || [])]) {
    const key = JSON.stringify(item);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    result.push(item);
  }

  return result.slice(-limit);
}

function sendJson(res, statusCode, payload) {
  const body = JSON.stringify(payload, null, 2);
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  });
  res.end(body);
}

function sendFile(req, res, filePath) {
  fs.readFile(filePath, (error, data) => {
    if (error) {
      sendJson(res, error.code === "ENOENT" ? 404 : 500, {
        status: "error",
        error_code: error.code === "ENOENT" ? "NOT_FOUND" : "STATIC_FILE_ERROR",
        message: error.message,
      });
      return;
    }

    const contentType = CONTENT_TYPES[path.extname(filePath).toLowerCase()] || "application/octet-stream";
    res.writeHead(200, {
      "Content-Type": contentType,
      "Content-Length": data.length,
    });
    res.end(req.method === "HEAD" ? undefined : data);
  });
}

function tryServeStatic(req, res, pathname) {
  if (req.method !== "GET" && req.method !== "HEAD") {
    return false;
  }

  const relativePath = pathname === "/" ? "index.html" : decodeURIComponent(pathname.slice(1));
  const filePath = path.resolve(MOBILE_WEB_DIR, relativePath);

  if (!filePath.startsWith(MOBILE_WEB_DIR)) {
    sendJson(res, 403, {
      status: "error",
      error_code: "FORBIDDEN",
      message: "Static path is outside mobile web directory",
    });
    return true;
  }

  if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
    return false;
  }

  sendFile(req, res, filePath);
  return true;
}

function readRequestBody(req, limit = 1024 * 1024) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];

    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > limit) {
        reject(new Error("Request body too large"));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });

    req.on("end", () => {
      const raw = Buffer.concat(chunks).toString("utf8").replace(/^\uFEFF/, "");
      if (!raw.trim()) {
        resolve({});
        return;
      }

      try {
        resolve(JSON.parse(raw));
      } catch (error) {
        reject(new Error(`Invalid JSON body: ${error.message}`));
      }
    });

    req.on("error", reject);
  });
}

function publicWorker(worker) {
  return {
    worker_id: worker.workerId,
    worker_name: worker.workerName,
    protocol_version: worker.protocolVersion,
    default_model: worker.defaultModel,
    available_models: worker.availableModels,
    max_concurrency: worker.maxConcurrency,
    running_tasks: worker.runningTasks,
    status: worker.status,
    connected_at: worker.connectedAt,
    last_heartbeat_at: worker.lastHeartbeatAt,
    remote_address: worker.remoteAddress,
  };
}

function getConnectedWorkers() {
  return [...workers.values()].filter((worker) => !worker.closed && worker.registered);
}

function selectWorker(model) {
  const connectedWorkers = getConnectedWorkers();
  if (!connectedWorkers.length) {
    return null;
  }

  if (model) {
    const modelWorker = connectedWorkers.find((worker) => worker.availableModels.includes(model));
    if (modelWorker) {
      return modelWorker;
    }
  }

  return connectedWorkers
    .slice()
    .sort((left, right) => left.runningTasks - right.runningTasks)[0];
}

function buildAITask(body) {
  const input = body.input || body.message;
  if (!input || typeof input !== "string") {
    throw new Error("message/input is required");
  }

  return {
    task_id: body.task_id || makeId("task"),
    task_type: body.task_type || "story_continue",
    user_id: body.user_id || "local_user",
    session_id: body.session_id || "local_session",
    story_id: body.story_id || "local_story",
    model: body.model || undefined,
    timeout_ms: body.timeout_ms || 180000,
    input,
    generation_options: {
      num_predict: 220,
      temperature: 0.66,
      top_p: 0.85,
      repeat_penalty: 1.08,
      think: false,
      ...(body.generation_options || body.options || {}),
    },
    context: {
      story_title: "黑夜古堡",
      world_setting: "中世纪奇幻世界",
      character_setting: "用户是失忆的贵族继承人",
      recent_messages: [],
      ...(body.context || {}),
    },
  };
}

async function handleListStories(req, res) {
  if (!database.pool) {
    sendJson(res, 200, {
      persistence_enabled: false,
      stories: [],
    });
    return;
  }

  const url = new URL(req.url, `http://${req.headers.host || `${HOST}:${PORT}`}`);
  const userId = cleanText(url.searchParams.get("user_id"), "local_user");

  try {
    const result = await database.pool.query(
      `
      SELECT
        s.id,
        s.user_id,
        s.title,
        s.world_setting,
        s.character_setting,
        s.default_model,
        s.generation_options,
        s.created_at,
        s.updated_at,
        COUNT(sess.id)::integer AS session_count
      FROM stories s
      LEFT JOIN sessions sess ON sess.story_id = s.id AND sess.status <> 'deleted'
      WHERE s.user_id = $1
      GROUP BY s.id
      ORDER BY s.updated_at DESC, s.created_at DESC
      LIMIT 100
      `,
      [userId],
    );

    sendJson(res, 200, {
      persistence_enabled: true,
      stories: result.rows,
    });
  } catch (error) {
    sendJson(res, 500, {
      status: "error",
      error_code: "DB_READ_FAILED",
      message: error.message,
    });
  }
}

async function handleCreateStory(req, res) {
  if (!requireDatabase(res)) {
    return;
  }

  let body;
  try {
    body = await readRequestBody(req);
  } catch (error) {
    sendJson(res, 400, {
      status: "error",
      error_code: "INVALID_REQUEST_BODY",
      message: error.message,
    });
    return;
  }

  const userId = cleanText(body.user_id, "local_user");
  const storyId = cleanText(body.story_id || body.id, makeId("story"));
  const title = cleanText(body.title, "新的故事");
  const worldSetting = cleanText(body.world_setting, "");
  const characterSetting = cleanText(body.character_setting, "");
  const defaultModel = cleanText(body.default_model || body.model, null);
  const generationOptions = body.generation_options || {};

  try {
    const story = await withDbTransaction(async (client) => {
      await ensureUser(client, userId);
      const result = await client.query(
        `
        INSERT INTO stories (
          id,
          user_id,
          title,
          world_setting,
          character_setting,
          default_model,
          generation_options
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
        ON CONFLICT (id) DO UPDATE
        SET
          title = EXCLUDED.title,
          world_setting = EXCLUDED.world_setting,
          character_setting = EXCLUDED.character_setting,
          default_model = EXCLUDED.default_model,
          generation_options = EXCLUDED.generation_options
        RETURNING *
        `,
        [storyId, userId, title, worldSetting, characterSetting, defaultModel, jsonParam(generationOptions)],
      );
      return result.rows[0];
    });

    sendJson(res, 201, {
      status: "success",
      story,
    });
  } catch (error) {
    sendJson(res, 500, {
      status: "error",
      error_code: "DB_WRITE_FAILED",
      message: error.message,
    });
  }
}

async function handleListStorySessions(req, res, storyId) {
  if (!database.pool) {
    sendJson(res, 200, {
      persistence_enabled: false,
      story_id: storyId,
      sessions: [],
    });
    return;
  }

  const url = new URL(req.url, `http://${req.headers.host || `${HOST}:${PORT}`}`);
  const userId = cleanText(url.searchParams.get("user_id"), "local_user");

  try {
    const result = await database.pool.query(
      `
      SELECT
        sess.id,
        sess.user_id,
        sess.story_id,
        sess.title,
        sess.status,
        sess.created_at,
        sess.updated_at,
        COUNT(msg.id)::integer AS message_count
      FROM sessions sess
      LEFT JOIN messages msg ON msg.session_id = sess.id
      WHERE sess.story_id = $1 AND sess.user_id = $2 AND sess.status <> 'deleted'
      GROUP BY sess.id
      ORDER BY sess.updated_at DESC, sess.created_at DESC
      LIMIT 100
      `,
      [storyId, userId],
    );

    sendJson(res, 200, {
      persistence_enabled: true,
      story_id: storyId,
      sessions: result.rows,
    });
  } catch (error) {
    sendJson(res, 500, {
      status: "error",
      error_code: "DB_READ_FAILED",
      message: error.message,
    });
  }
}

async function handleCreateStorySession(req, res, storyId) {
  if (!requireDatabase(res)) {
    return;
  }

  let body;
  try {
    body = await readRequestBody(req);
  } catch (error) {
    sendJson(res, 400, {
      status: "error",
      error_code: "INVALID_REQUEST_BODY",
      message: error.message,
    });
    return;
  }

  const userId = cleanText(body.user_id, "local_user");
  const sessionId = cleanText(body.session_id || body.id, makeId("session"));
  const title = cleanText(body.title, "新的会话");

  try {
    const session = await withDbTransaction(async (client) => {
      const storyResult = await client.query(
        `
        SELECT id
        FROM stories
        WHERE id = $1 AND user_id = $2
        `,
        [storyId, userId],
      );
      if (!storyResult.rows.length) {
        throw new Error(`Story not found: ${storyId}`);
      }

      const result = await client.query(
        `
        INSERT INTO sessions (id, user_id, story_id, title, status)
        VALUES ($1, $2, $3, $4, 'active')
        ON CONFLICT (id) DO UPDATE
        SET
          title = EXCLUDED.title,
          status = 'active',
          story_id = EXCLUDED.story_id
        RETURNING *
        `,
        [sessionId, userId, storyId, title],
      );
      return result.rows[0];
    });

    sendJson(res, 201, {
      status: "success",
      session,
    });
  } catch (error) {
    sendJson(res, error.message.startsWith("Story not found") ? 404 : 500, {
      status: "error",
      error_code: error.message.startsWith("Story not found") ? "STORY_NOT_FOUND" : "DB_WRITE_FAILED",
      message: error.message,
    });
  }
}

async function handleUpdateSession(req, res, sessionId) {
  if (!requireDatabase(res)) {
    return;
  }

  let body;
  try {
    body = await readRequestBody(req);
  } catch (error) {
    sendJson(res, 400, {
      status: "error",
      error_code: "INVALID_REQUEST_BODY",
      message: error.message,
    });
    return;
  }

  const title = cleanText(body.title, null);
  const status = cleanText(body.status, null);
  if (!title && !status) {
    sendJson(res, 400, {
      status: "error",
      error_code: "INVALID_REQUEST",
      message: "title or status is required",
    });
    return;
  }
  if (status && !["active", "archived", "deleted"].includes(status)) {
    sendJson(res, 400, {
      status: "error",
      error_code: "INVALID_STATUS",
      message: "status must be active, archived, or deleted",
    });
    return;
  }

  try {
    const result = await database.pool.query(
      `
      UPDATE sessions
      SET
        title = COALESCE($2, title),
        status = COALESCE($3, status)
      WHERE id = $1
      RETURNING *
      `,
      [sessionId, title, status],
    );

    if (!result.rows.length) {
      sendJson(res, 404, {
        status: "error",
        error_code: "SESSION_NOT_FOUND",
        message: `Session not found: ${sessionId}`,
      });
      return;
    }

    sendJson(res, 200, {
      status: "success",
      session: result.rows[0],
    });
  } catch (error) {
    sendJson(res, 500, {
      status: "error",
      error_code: "DB_WRITE_FAILED",
      message: error.message,
    });
  }
}

async function handleDeleteSession(req, res, sessionId) {
  if (!requireDatabase(res)) {
    return;
  }

  try {
    const result = await database.pool.query(
      `
      UPDATE sessions
      SET status = 'deleted'
      WHERE id = $1
      RETURNING *
      `,
      [sessionId],
    );

    if (!result.rows.length) {
      sendJson(res, 404, {
        status: "error",
        error_code: "SESSION_NOT_FOUND",
        message: `Session not found: ${sessionId}`,
      });
      return;
    }

    sendJson(res, 200, {
      status: "success",
      session: result.rows[0],
    });
  } catch (error) {
    sendJson(res, 500, {
      status: "error",
      error_code: "DB_WRITE_FAILED",
      message: error.message,
    });
  }
}

async function handleStoryContinue(req, res) {
  let body;
  try {
    body = await readRequestBody(req);
  } catch (error) {
    sendJson(res, 400, {
      status: "error",
      error_code: "INVALID_REQUEST_BODY",
      message: error.message,
    });
    return;
  }

  let task;
  try {
    task = buildAITask(body);
  } catch (error) {
    sendJson(res, 400, {
      status: "error",
      error_code: "INVALID_REQUEST",
      message: error.message,
    });
    return;
  }

  const worker = selectWorker(task.model);
  if (!worker) {
    sendJson(res, 503, {
      task_id: task.task_id,
      status: "error",
      error_code: task.model ? "MODEL_WORKER_NOT_AVAILABLE" : "NO_WORKER_AVAILABLE",
      message: task.model
        ? `没有可用 Worker 提供模型：${task.model}`
        : "没有可用 Worker，请先启动本地 AI Worker",
    });
    return;
  }

  const requestId = makeId("req_story");
  const timeoutMs = Number(body.server_timeout_ms || SERVER_TASK_TIMEOUT);
  console.log(`[server] Dispatch task ${task.task_id} to worker ${worker.workerId}, timeout=${timeoutMs}ms`);

  try {
    // Load story state and include it in the task context
    const storyState = await getStoryState(task.session_id);
    if (storyState) {
      task.context.story_state = storyState.state;
      task.context.story_state_version = storyState.version;
    } else {
      // Initialize empty story state if none exists
      task.context.story_state = {
        current_world: "default_world",
        current_scene: "",
        story_stage: "opening",
        long_summary: "",
        characters: {},
        relationships: {},
        world_flags: {},
        inventory: [],
        pending_events: []
      };
      task.context.story_state_version = 0;
    }

    if (database.pool) {
      const messagesResult = await database.pool.query(
        `
        SELECT role, content
        FROM messages
        WHERE session_id = $1
        ORDER BY created_at ASC, id ASC
        LIMIT 20
        `,
        [task.session_id],
      );
      task.context.recent_messages = messagesResult.rows.map(row => ({
        role: row.role,
        content: row.content
      }));
    }

    await persistTaskDispatch(task, worker, requestId, timeoutMs);
  } catch (error) {
    console.error(`[server] Failed to persist task dispatch ${task.task_id}:`, error);
    sendJson(res, 500, {
      task_id: task.task_id,
      status: "error",
      error_code: "DB_PERSIST_FAILED",
      message: error.message,
    });
    return;
  }

  const resultPromise = new Promise((resolve) => {
    const timeout = setTimeout(() => {
      console.warn(`[server] Task timeout: ${task.task_id}`);
      const pending = pendingTasks.get(task.task_id);
      pendingTasks.delete(task.task_id);
      worker.runningTasks = Math.max(worker.runningTasks - 1, 0);
      worker.send("ai.task_cancel", {
        task_id: task.task_id,
        reason: "server_timeout",
      }, requestId);
      const timeoutPayload = {
        task_id: task.task_id,
        status: "error",
        model: task.model,
        worker_id: worker.workerId,
        error_code: "TASK_TIMEOUT",
        message: `Server 等待 Worker 结果超时：${timeoutMs} ms`,
        retryable: true,
      };
      void persistTaskError(pending, timeoutPayload, "timeout").catch((error) => {
        console.error(`[server] Failed to persist task timeout ${task.task_id}:`, error);
      });
      resolve({
        httpStatus: 504,
        payload: timeoutPayload,
      });
    }, timeoutMs);

    pendingTasks.set(task.task_id, {
      taskId: task.task_id,
      task,
      requestId,
      workerId: worker.workerId,
      startedAt: Date.now(),
      timeout,
      resolve,
    });
  });

  worker.runningTasks += 1;
  worker.send("ai.task", task, requestId);
  console.log(`[server] ai.task sent: ${task.task_id}`);

  const result = await resultPromise;
  sendJson(res, result.httpStatus, result.payload);
}

async function handleGetStoryState(req, res, sessionId) {
  if (!database.pool) {
    sendJson(res, 200, {
      session_id: sessionId,
      persistence_enabled: false,
      story_state: null,
    });
    return;
  }

  try {
    const storyState = await getStoryState(sessionId);
    sendJson(res, 200, {
      session_id: sessionId,
      persistence_enabled: true,
      story_state: storyState ? storyState.state : null,
      version: storyState ? storyState.version : 0,
      created_at: storyState ? storyState.created_at : null,
      updated_at: storyState ? storyState.updated_at : null,
    });
  } catch (error) {
    sendJson(res, 500, {
      status: "error",
      error_code: "DB_READ_FAILED",
      message: error.message,
    });
  }
}

async function handleUpdateStoryState(req, res, sessionId) {
  let body;
  try {
    body = await readRequestBody(req);
  } catch (error) {
    sendJson(res, 400, {
      status: "error",
      error_code: "INVALID_REQUEST_BODY",
      message: error.message,
    });
    return;
  }

  if (!database.pool) {
    sendJson(res, 200, {
      session_id: sessionId,
      persistence_enabled: false,
      story_state: body.state || {},
    });
    return;
  }

  try {
    const { user_id, story_id, state } = body;
    if (!state || typeof state !== 'object') {
      sendJson(res, 400, {
        status: "error",
        error_code: "INVALID_STATE",
        message: "state object is required",
      });
      return;
    }

    const result = await updateStoryState(sessionId, user_id || "local_user", story_id || "local_story", state);
    sendJson(res, 200, {
      session_id: sessionId,
      persistence_enabled: true,
      story_state: result ? result.state : state,
      version: result ? result.version : 0,
      updated_at: result ? null : new Date().toISOString(),
    });
  } catch (error) {
    sendJson(res, 500, {
      status: "error",
      error_code: "DB_UPDATE_FAILED",
      message: error.message,
    });
  }
}

async function completePendingTask(message) {
  const payload = message.payload || {};
  const taskId = payload.task_id;
  if (!taskId) {
    return false;
  }

  const pending = pendingTasks.get(taskId);
  if (!pending) {
    console.warn(`[server] Late or unknown task result ignored: ${taskId}`);
    return false;
  }

  pendingTasks.delete(taskId);
  clearTimeout(pending.timeout);
  console.log(`[server] Complete task ${taskId} with ${message.type}`);

  const worker = workers.get(pending.workerId);
  if (worker) {
    worker.runningTasks = Math.max(worker.runningTasks - 1, 0);
  }

  const statusCode = message.type === "ai.result" ? 200 : errorCodeToHttpStatus(payload.error_code);
  const responsePayload = {
    ...payload,
    request_id: message.request_id,
  };

  try {
    if (message.type === "ai.result") {
      await persistTaskSuccess(pending, message, responsePayload);
    } else {
      await persistTaskError(pending, responsePayload, "error");
    }
  } catch (error) {
    console.error(`[server] Failed to persist task result ${taskId}:`, error);
    responsePayload.persistence_error = error.message;
  }

  pending.resolve({
    httpStatus: statusCode,
    payload: responsePayload,
  });
  return true;
}

function errorCodeToHttpStatus(errorCode) {
  switch (errorCode) {
    case "MODEL_NOT_FOUND":
      return 400;
    case "WORKER_BUSY":
      return 503;
    case "OLLAMA_TIMEOUT":
    case "TASK_TIMEOUT":
      return 504;
    case "GENERATION_QUALITY_FAILED":
      return 422;
    default:
      return 500;
  }
}

function handleRequest(req, res) {
  const url = new URL(req.url, `http://${req.headers.host || `${HOST}:${PORT}`}`);

  if (req.method === "OPTIONS") {
    sendJson(res, 204, {});
    return;
  }

  if (req.method === "GET" && url.pathname === "/health") {
    handleHealth(req, res).catch((error) => {
      console.error("[server] Health check failed:", error);
      sendJson(res, 500, {
        status: "error",
        error_code: "HEALTH_CHECK_FAILED",
        message: error.message,
      });
    });
    return;
  }

  if (req.method === "GET" && url.pathname === "/workers") {
    sendJson(res, 200, {
      workers: getConnectedWorkers().map(publicWorker),
    });
    return;
  }

  if (url.pathname === "/api/stories") {
    if (req.method === "GET") {
      handleListStories(req, res);
      return;
    }
    if (req.method === "POST") {
      handleCreateStory(req, res);
      return;
    }
  }

  const storySessionsMatch = url.pathname.match(/^\/api\/stories\/([^/]+)\/sessions$/);
  if (storySessionsMatch) {
    const storyId = decodeURIComponent(storySessionsMatch[1]);
    if (req.method === "GET") {
      handleListStorySessions(req, res, storyId);
      return;
    }
    if (req.method === "POST") {
      handleCreateStorySession(req, res, storyId);
      return;
    }
  }

  const sessionMatch = url.pathname.match(/^\/api\/sessions\/([^/]+)$/);
  if (sessionMatch) {
    const sessionId = decodeURIComponent(sessionMatch[1]);
    if (req.method === "PUT") {
      handleUpdateSession(req, res, sessionId);
      return;
    }
    if (req.method === "DELETE") {
      handleDeleteSession(req, res, sessionId);
      return;
    }
  }

  const sessionMessagesMatch = url.pathname.match(/^\/api\/sessions\/([^/]+)\/messages$/);
  if (req.method === "GET" && sessionMessagesMatch) {
    handleSessionMessages(req, res, decodeURIComponent(sessionMessagesMatch[1]));
    return;
  }

  if (req.method === "POST" && url.pathname === "/api/story/continue") {
    handleStoryContinue(req, res).catch((error) => {
      console.error("[server] Story continue failed:", error);
      sendJson(res, 500, {
        status: "error",
        error_code: "SERVER_ERROR",
        message: error.message,
      });
    });
    return;
  }

  const storyStateMatch = url.pathname.match(/^\/api\/story\/state\/([^/]+)$/);
  if (storyStateMatch) {
    const sessionId = decodeURIComponent(storyStateMatch[1]);
    if (req.method === "GET") {
      handleGetStoryState(req, res, sessionId).catch((error) => {
        console.error("[server] Get story state failed:", error);
        sendJson(res, 500, {
          status: "error",
          error_code: "SERVER_ERROR",
          message: error.message,
        });
      });
      return;
    }
    if (req.method === "PUT") {
      handleUpdateStoryState(req, res, sessionId).catch((error) => {
        console.error("[server] Update story state failed:", error);
        sendJson(res, 500, {
          status: "error",
          error_code: "SERVER_ERROR",
          message: error.message,
        });
      });
      return;
    }
  }

  if (tryServeStatic(req, res, url.pathname)) {
    return;
  }

  sendJson(res, 404, {
    status: "error",
    error_code: "NOT_FOUND",
    message: `No route for ${req.method} ${url.pathname}`,
  });
}

class WorkerConnection {
  constructor(socket) {
    this.socket = socket;
    this.id = makeId("conn");
    this.workerId = this.id;
    this.workerName = null;
    this.protocolVersion = null;
    this.defaultModel = null;
    this.availableModels = [];
    this.maxConcurrency = 1;
    this.runningTasks = 0;
    this.status = "connected";
    this.connectedAt = nowIso();
    this.lastHeartbeatAt = null;
    this.remoteAddress = socket.remoteAddress;
    this.registered = false;
    this.closed = false;
    this.buffer = Buffer.alloc(0);

    socket.on("data", (chunk) => this.onData(chunk));
    socket.on("close", () => this.onClose());
    socket.on("error", (error) => {
      console.warn(`[server] Worker socket error: ${error.message}`);
    });
  }

  onData(chunk) {
    this.buffer = Buffer.concat([this.buffer, chunk]);

    while (true) {
      const frame = readFrame(this.buffer);
      if (!frame) {
        return;
      }

      this.buffer = this.buffer.subarray(frame.bytesRead);
      this.handleFrame(frame);
    }
  }

  handleFrame(frame) {
    if (frame.opcode === 0x8) {
      this.close();
      return;
    }

    if (frame.opcode === 0x9) {
      this.sendFrame(frame.payload, 0xA);
      return;
    }

    if (frame.opcode !== 0x1) {
      return;
    }

    let message;
    try {
      message = JSON.parse(frame.payload.toString("utf8"));
    } catch (error) {
      this.send("error", {
        error_code: "INVALID_MESSAGE",
        message: `JSON 解析失败：${error.message}`,
      });
      return;
    }

    this.handleMessage(message);
  }

  handleMessage(message) {
    const type = message.type;
    const payload = message.payload || {};

    if (!type) {
      this.send("error", {
        error_code: "INVALID_MESSAGE",
        message: "消息缺少 type 字段",
      }, message.request_id);
      return;
    }

    if (type === "worker.register") {
      this.handleRegister(payload, message.request_id);
      return;
    }

    if (type === "worker.heartbeat") {
      this.handleHeartbeat(payload, message.request_id);
      return;
    }

    if (type === "ai.result" || type === "ai.task_error") {
      console.log(`[server] Worker message: ${type} task=${payload.task_id || ""}`);
      void completePendingTask(message).catch((error) => {
        console.error("[server] Complete pending task failed:", error);
      });
      return;
    }

    if (type === "error") {
      console.warn("[server] Worker protocol error:", payload);
      return;
    }

    this.send("error", {
      error_code: "UNSUPPORTED_MESSAGE_TYPE",
      message: `不支持的消息类型：${type}`,
    }, message.request_id);
  }

  handleRegister(payload, requestId) {
    this.workerId = String(payload.worker_id || this.id);
    this.workerName = payload.worker_name || null;
    this.protocolVersion = payload.protocol_version || null;
    this.defaultModel = payload.default_model || null;
    this.availableModels = Array.isArray(payload.available_models) ? payload.available_models : [];
    this.maxConcurrency = Number(payload.max_concurrency || 1);
    this.status = "idle";
    this.registered = true;
    this.lastHeartbeatAt = nowIso();

    const existing = workers.get(this.workerId);
    if (existing && existing !== this) {
      existing.close();
    }

    workers.set(this.workerId, this);
    console.log(`[server] Worker registered: ${this.workerId}`);

    this.send("worker.registered", {
      worker_id: this.workerId,
      server_id: "dreamweave-local-server",
      heartbeat_interval_ms: HEARTBEAT_INTERVAL,
      task_timeout_ms: 180000,
    }, requestId);
  }

  handleHeartbeat(payload, requestId) {
    this.status = payload.status || this.status;
    this.runningTasks = Number(payload.running_tasks ?? this.runningTasks);
    this.maxConcurrency = Number(payload.max_concurrency || this.maxConcurrency);
    this.defaultModel = payload.default_model || this.defaultModel;
    this.availableModels = Array.isArray(payload.available_models) ? payload.available_models : this.availableModels;
    this.lastHeartbeatAt = nowIso();

    this.send("worker.heartbeat_ack", {
      worker_id: this.workerId,
    }, requestId);
  }

  send(type, payload, requestId) {
    const message = makeMessage(type, payload, requestId);
    this.sendText(JSON.stringify(message));
  }

  sendText(text) {
    this.sendFrame(Buffer.from(text, "utf8"), 0x1);
  }

  sendFrame(payload, opcode) {
    if (this.closed || this.socket.destroyed) {
      return;
    }

    this.socket.write(createFrame(payload, opcode));
  }

  close() {
    if (this.closed) {
      return;
    }
    this.closed = true;

    try {
      this.socket.end(createFrame(Buffer.alloc(0), 0x8));
    } catch {
      this.socket.destroy();
    }
  }

  onClose() {
    this.closed = true;
    if (workers.get(this.workerId) === this) {
      workers.delete(this.workerId);
    }

    for (const [taskId, pending] of pendingTasks.entries()) {
      if (pending.workerId !== this.workerId) {
        continue;
      }

      pendingTasks.delete(taskId);
      clearTimeout(pending.timeout);
      const payload = {
        task_id: taskId,
        status: "error",
        worker_id: this.workerId,
        error_code: "WORKER_DISCONNECTED",
        message: "Worker 连接已断开",
        retryable: true,
      };
      void persistTaskError(pending, payload, "error").catch((error) => {
        console.error(`[server] Failed to persist worker disconnect ${taskId}:`, error);
      });
      pending.resolve({
        httpStatus: 503,
        payload,
      });
    }

    console.log(`[server] Worker disconnected: ${this.workerId}`);
  }
}

function readFrame(buffer) {
  if (buffer.length < 2) {
    return null;
  }

  const first = buffer[0];
  const second = buffer[1];
  const opcode = first & 0x0f;
  const masked = (second & 0x80) !== 0;
  let length = second & 0x7f;
  let offset = 2;

  if (length === 126) {
    if (buffer.length < offset + 2) {
      return null;
    }
    length = buffer.readUInt16BE(offset);
    offset += 2;
  } else if (length === 127) {
    if (buffer.length < offset + 8) {
      return null;
    }
    const longLength = buffer.readBigUInt64BE(offset);
    if (longLength > BigInt(Number.MAX_SAFE_INTEGER)) {
      throw new Error("WebSocket frame too large");
    }
    length = Number(longLength);
    offset += 8;
  }

  let mask;
  if (masked) {
    if (buffer.length < offset + 4) {
      return null;
    }
    mask = buffer.subarray(offset, offset + 4);
    offset += 4;
  }

  if (buffer.length < offset + length) {
    return null;
  }

  const payload = Buffer.from(buffer.subarray(offset, offset + length));
  if (mask) {
    for (let index = 0; index < payload.length; index += 1) {
      payload[index] ^= mask[index % 4];
    }
  }

  return {
    opcode,
    payload,
    bytesRead: offset + length,
  };
}

function createFrame(payload, opcode = 0x1) {
  const length = payload.length;
  let header;

  if (length < 126) {
    header = Buffer.alloc(2);
    header[1] = length;
  } else if (length < 65536) {
    header = Buffer.alloc(4);
    header[1] = 126;
    header.writeUInt16BE(length, 2);
  } else {
    header = Buffer.alloc(10);
    header[1] = 127;
    header.writeBigUInt64BE(BigInt(length), 2);
  }

  header[0] = 0x80 | opcode;
  return Buffer.concat([header, payload]);
}

function handleUpgrade(req, socket) {
  const url = new URL(req.url, `http://${req.headers.host || `${HOST}:${PORT}`}`);
  if (url.pathname !== WORKER_PATH) {
    socket.write("HTTP/1.1 404 Not Found\r\n\r\n");
    socket.destroy();
    return;
  }

  const key = req.headers["sec-websocket-key"];
  if (!key) {
    socket.write("HTTP/1.1 400 Bad Request\r\n\r\n");
    socket.destroy();
    return;
  }

  const accept = crypto.createHash("sha1").update(`${key}${WS_GUID}`).digest("base64");
  socket.write(
    [
      "HTTP/1.1 101 Switching Protocols",
      "Upgrade: websocket",
      "Connection: Upgrade",
      `Sec-WebSocket-Accept: ${accept}`,
      "\r\n",
    ].join("\r\n"),
  );

  new WorkerConnection(socket);
}

setInterval(() => {
  const now = Date.now();
  for (const worker of workers.values()) {
    if (!worker.lastHeartbeatAt) {
      continue;
    }

    const lastHeartbeatAt = Date.parse(worker.lastHeartbeatAt);
    if (Number.isFinite(lastHeartbeatAt) && now - lastHeartbeatAt > WORKER_OFFLINE_TIMEOUT) {
      worker.status = "offline";
    }
  }
}, Math.min(HEARTBEAT_INTERVAL, 10000));

const server = http.createServer(handleRequest);
server.on("upgrade", handleUpgrade);

server.listen(PORT, HOST, () => {
  console.log(`[server] DreamWeave server listening on http://${HOST}:${PORT}`);
  console.log(`[server] Worker WebSocket endpoint ws://${HOST}:${PORT}${WORKER_PATH}`);
});
