"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { URL } = require("node:url");

const WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
const HOST = process.env.DREAMWEAVE_SERVER_HOST || "127.0.0.1";
const PORT = Number(process.env.DREAMWEAVE_SERVER_PORT || 3000);
const WORKER_PATH = process.env.DREAMWEAVE_WORKER_PATH || "/ws/worker";
const SERVER_TASK_TIMEOUT = Number(process.env.DREAMWEAVE_SERVER_TASK_TIMEOUT || 200000);
const HEARTBEAT_INTERVAL = Number(process.env.DREAMWEAVE_HEARTBEAT_INTERVAL || 15000);
const WORKER_OFFLINE_TIMEOUT = Number(process.env.DREAMWEAVE_WORKER_OFFLINE_TIMEOUT || 45000);

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

function sendJson(res, statusCode, payload) {
  const body = JSON.stringify(payload, null, 2);
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
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

  const resultPromise = new Promise((resolve) => {
    const timeout = setTimeout(() => {
      console.warn(`[server] Task timeout: ${task.task_id}`);
      pendingTasks.delete(task.task_id);
      worker.send("ai.task_cancel", {
        task_id: task.task_id,
        reason: "server_timeout",
      }, requestId);
      resolve({
        httpStatus: 504,
        payload: {
          task_id: task.task_id,
          status: "error",
          model: task.model,
          worker_id: worker.workerId,
          error_code: "TASK_TIMEOUT",
          message: `Server 等待 Worker 结果超时：${timeoutMs} ms`,
          retryable: true,
        },
      });
    }, timeoutMs);

    pendingTasks.set(task.task_id, {
      taskId: task.task_id,
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

function completePendingTask(message) {
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
  pending.resolve({
    httpStatus: statusCode,
    payload: {
      ...payload,
      request_id: message.request_id,
    },
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
    sendJson(res, 200, {
      status: "ok",
      server_time: nowIso(),
      worker_count: getConnectedWorkers().length,
      pending_task_count: pendingTasks.size,
      workers: getConnectedWorkers().map(publicWorker),
    });
    return;
  }

  if (req.method === "GET" && url.pathname === "/workers") {
    sendJson(res, 200, {
      workers: getConnectedWorkers().map(publicWorker),
    });
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
      completePendingTask(message);
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
      pending.resolve({
        httpStatus: 503,
        payload: {
          task_id: taskId,
          status: "error",
          worker_id: this.workerId,
          error_code: "WORKER_DISCONNECTED",
          message: "Worker 连接已断开",
          retryable: true,
        },
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
