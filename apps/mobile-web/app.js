"use strict";

const API_BASE = window.location.protocol === "file:" ? "http://127.0.0.1:3000" : "";
const STORAGE_KEY = "dreamweave.mobile.v1";

const state = {
  messages: [],
  model: "qwen3:14b",
  workerReady: false,
  sending: false,
};

const elements = {
  connectionStatus: document.querySelector("#connectionStatus"),
  workerStatus: document.querySelector("#workerStatus"),
  settingsToggle: document.querySelector("#settingsToggle"),
  settingsPanel: document.querySelector("#settingsPanel"),
  modelSelect: document.querySelector("#modelSelect"),
  storyTitle: document.querySelector("#storyTitle"),
  storyTitleDisplay: document.querySelector("#storyTitleDisplay"),
  worldSetting: document.querySelector("#worldSetting"),
  characterSetting: document.querySelector("#characterSetting"),
  messageList: document.querySelector("#messageList"),
  composer: document.querySelector("#composer"),
  messageInput: document.querySelector("#messageInput"),
  sendButton: document.querySelector("#sendButton"),
};

function loadState() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return;
  }

  try {
    const saved = JSON.parse(raw);
    state.messages = Array.isArray(saved.messages) ? saved.messages : [];
    elements.storyTitle.value = saved.storyTitle || elements.storyTitle.value;
    elements.worldSetting.value = saved.worldSetting || elements.worldSetting.value;
    elements.characterSetting.value = saved.characterSetting || elements.characterSetting.value;
    state.model = saved.model || state.model;
  } catch {
    localStorage.removeItem(STORAGE_KEY);
  }
}

function saveState() {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      messages: state.messages.slice(-30),
      model: state.model,
      storyTitle: elements.storyTitle.value,
      worldSetting: elements.worldSetting.value,
      characterSetting: elements.characterSetting.value,
    }),
  );
}

function setStatus(text, ready) {
  state.workerReady = Boolean(ready);
  elements.connectionStatus.textContent = text;
  elements.workerStatus.textContent = ready ? "Worker 在线" : "Worker 未连接";
  updateSendState();
}

function updateSendState() {
  const hasMessage = elements.messageInput.value.trim().length > 0;
  elements.sendButton.disabled = state.sending || !state.workerReady || !hasMessage;
}

function renderMessages() {
  elements.messageList.replaceChildren();

  if (!state.messages.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.innerHTML = "<strong>黑夜古堡</strong><span>大门紧闭，冷风从石阶下卷过。</span>";
    elements.messageList.append(empty);
    return;
  }

  for (const item of state.messages) {
    const node = document.createElement("article");
    node.className = `message ${item.role}`;
    node.textContent = item.content;
    elements.messageList.append(node);
  }

  elements.messageList.scrollTop = elements.messageList.scrollHeight;
}

function setLoadingMessage(visible) {
  const existing = document.querySelector("[data-loading-message]");
  if (existing) {
    existing.remove();
  }

  if (!visible) {
    return;
  }

  const node = document.createElement("article");
  node.className = "message assistant loading";
  node.dataset.loadingMessage = "true";
  node.textContent = "墨迹正在浮现。";
  elements.messageList.append(node);
  elements.messageList.scrollTop = elements.messageList.scrollHeight;
}

async function refreshHealth() {
  try {
    const response = await fetch(`${API_BASE}/health`, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const health = await response.json();
    const workers = Array.isArray(health.workers) ? health.workers : [];
    const models = [...new Set(workers.flatMap((worker) => worker.available_models || []))];

    if (models.length) {
      updateModelOptions(models);
    }

    setStatus(workers.length ? "已连接" : "等待 Worker", workers.length > 0);
  } catch {
    setStatus("Server 未连接", false);
  }
}

function updateModelOptions(models) {
  const current = state.model;
  elements.modelSelect.replaceChildren();

  for (const model of models) {
    const option = document.createElement("option");
    option.value = model;
    option.textContent = model;
    elements.modelSelect.append(option);
  }

  state.model = models.includes(current) ? current : models[0];
  elements.modelSelect.value = state.model;
  saveState();
}

function buildRecentMessages() {
  return state.messages.slice(-8).map((item) => {
    const role = item.role === "user" ? "用户" : "剧情";
    return `${role}：${item.content}`;
  });
}

async function submitMessage(message) {
  const userMessage = {
    role: "user",
    content: message,
    createdAt: new Date().toISOString(),
  };

  state.messages.push(userMessage);
  state.sending = true;
  saveState();
  renderMessages();
  setLoadingMessage(true);
  updateSendState();

  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 220000);

  try {
    const response = await fetch(`${API_BASE}/api/story/continue`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      signal: controller.signal,
      body: JSON.stringify({
        user_id: "local_user",
        session_id: "local_session",
        story_id: "local_story",
        model: state.model,
        message,
        timeout_ms: 180000,
        generation_options: {
          num_predict: 220,
          temperature: 0.66,
          top_p: 0.85,
          repeat_penalty: 1.08,
          think: false,
        },
        context: {
          story_title: elements.storyTitle.value.trim() || "黑夜古堡",
          world_setting: elements.worldSetting.value.trim() || "中世纪奇幻世界",
          character_setting: elements.characterSetting.value.trim() || "用户是失忆的贵族继承人",
          recent_messages: buildRecentMessages(),
        },
      }),
    });

    const result = await response.json();
    if (!response.ok || result.status === "error") {
      throw new Error(result.message || result.error_code || `HTTP ${response.status}`);
    }

    state.messages.push({
      role: "assistant",
      content: result.content,
      model: result.model,
      taskId: result.task_id,
      createdAt: new Date().toISOString(),
    });
  } catch (error) {
    state.messages.push({
      role: "error",
      content: error.name === "AbortError" ? "生成超时，请稍后重试。" : error.message,
      createdAt: new Date().toISOString(),
    });
  } finally {
    window.clearTimeout(timeout);
    state.sending = false;
    saveState();
    renderMessages();
    updateSendState();
  }
}

function bindEvents() {
  elements.settingsToggle.addEventListener("click", () => {
    elements.settingsPanel.hidden = !elements.settingsPanel.hidden;
  });

  elements.modelSelect.addEventListener("change", () => {
    state.model = elements.modelSelect.value;
    saveState();
  });

  elements.storyTitle.addEventListener("input", () => {
    elements.storyTitleDisplay.textContent = elements.storyTitle.value.trim() || "未命名故事";
    saveState();
  });

  for (const input of [elements.worldSetting, elements.characterSetting]) {
    input.addEventListener("input", saveState);
  }

  elements.messageInput.addEventListener("input", updateSendState);

  elements.messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      elements.composer.requestSubmit();
    }
  });

  elements.composer.addEventListener("submit", (event) => {
    event.preventDefault();
    const message = elements.messageInput.value.trim();
    if (!message || state.sending || !state.workerReady) {
      return;
    }

    elements.messageInput.value = "";
    updateSendState();
    submitMessage(message);
  });
}

function init() {
  loadState();
  elements.modelSelect.value = state.model;
  elements.storyTitleDisplay.textContent = elements.storyTitle.value.trim() || "黑夜古堡";
  bindEvents();
  renderMessages();
  updateSendState();
  refreshHealth();
  window.setInterval(refreshHealth, 10000);
}

init();
