"use strict";

const API_BASE = window.location.protocol === "file:" ? "http://127.0.0.1:3000" : "";
const STORAGE_KEY = "dreamweave.mobile.v1";
const DEFAULT_USER_ID = "local_user";
const DEFAULT_STORY_ID = "local_story";
const DEFAULT_SESSION_ID = "local_session";

const state = {
  userId: DEFAULT_USER_ID,
  storyId: DEFAULT_STORY_ID,
  sessionId: DEFAULT_SESSION_ID,
  stories: [],
  sessions: [],
  messages: [],
  storyState: null,
  storyStateVersion: 0,
  model: "qwen3:14b",
  workerReady: false,
  sending: false,
  savingSettings: false,
};

const elements = {
  connectionStatus: document.querySelector("#connectionStatus"),
  workerStatus: document.querySelector("#workerStatus"),
  libraryToggle: document.querySelector("#libraryToggle"),
  libraryPanel: document.querySelector("#libraryPanel"),
  storyList: document.querySelector("#storyList"),
  sessionList: document.querySelector("#sessionList"),
  newStoryButton: document.querySelector("#newStoryButton"),
  newSessionButton: document.querySelector("#newSessionButton"),
  settingsToggle: document.querySelector("#settingsToggle"),
  settingsPanel: document.querySelector("#settingsPanel"),
  modelSelect: document.querySelector("#modelSelect"),
  storyTitle: document.querySelector("#storyTitle"),
  storyTitleDisplay: document.querySelector("#storyTitleDisplay"),
  worldSetting: document.querySelector("#worldSetting"),
  characterSetting: document.querySelector("#characterSetting"),
  saveStorySettingsButton: document.querySelector("#saveStorySettingsButton"),
  settingsSaveStatus: document.querySelector("#settingsSaveStatus"),
  messageList: document.querySelector("#messageList"),
  storyStatePanel: document.querySelector("#storyStatePanel"),
  stateScene: document.querySelector("#stateScene"),
  stateStage: document.querySelector("#stateStage"),
  stateEvents: document.querySelector("#stateEvents"),
  stateSummary: document.querySelector("#stateSummary"),
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
    state.storyId = saved.storyId || state.storyId;
    state.sessionId = saved.sessionId || state.sessionId;
    elements.storyTitle.value = saved.storyTitle || elements.storyTitle.value;
    elements.worldSetting.value = saved.worldSetting || elements.worldSetting.value;
    elements.characterSetting.value = saved.characterSetting || elements.characterSetting.value;
    state.model = saved.model || state.model;
  } catch {
    localStorage.removeItem(STORAGE_KEY);
  }
}

async function loadSessionMessages() {
  try {
    const response = await fetch(`${API_BASE}/api/sessions/${encodeURIComponent(state.sessionId)}/messages`, {
      cache: "no-store",
    });
    if (!response.ok) {
      return;
    }

    const result = await response.json();
    if (!result.persistence_enabled || !Array.isArray(result.messages) || !result.messages.length) {
      return;
    }

    state.messages = result.messages
      .filter((item) => item.role === "user" || item.role === "assistant")
      .map((item) => ({
        role: item.role,
        content: item.content,
        model: item.model,
        taskId: item.task_id,
        createdAt: item.created_at,
      }));
    saveState();
    renderMessages();
  } catch {
    // Local storage remains the fallback when database history is unavailable.
  }
}

async function loadStoryState() {
  try {
    const response = await fetch(`${API_BASE}/api/story/state/${encodeURIComponent(state.sessionId)}`, {
      cache: "no-store",
    });
    if (!response.ok) {
      return;
    }

    const result = await response.json();
    if (!result.persistence_enabled || !result.story_state) {
      renderStoryState(null, 0);
      return;
    }

    renderStoryState(result.story_state, result.version || 0);
  } catch {
    renderStoryState(null, 0);
  }
}

async function loadLibrary() {
  await loadStories();
  await loadSessions();
}

async function loadStories() {
  try {
    const response = await fetch(`${API_BASE}/api/stories?user_id=${encodeURIComponent(state.userId)}`, {
      cache: "no-store",
    });
    if (!response.ok) {
      return;
    }

    const result = await response.json();
    state.stories = Array.isArray(result.stories) ? result.stories : [];
    renderStories();
  } catch {
    state.stories = [];
    renderStories();
  }
}

async function loadSessions() {
  try {
    const response = await fetch(
      `${API_BASE}/api/stories/${encodeURIComponent(state.storyId)}/sessions?user_id=${encodeURIComponent(state.userId)}`,
      { cache: "no-store" },
    );
    if (!response.ok) {
      return;
    }

    const result = await response.json();
    state.sessions = Array.isArray(result.sessions) ? result.sessions : [];
    renderSessions();
  } catch {
    state.sessions = [];
    renderSessions();
  }
}

function saveState() {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      messages: state.messages.slice(-30),
      storyId: state.storyId,
      sessionId: state.sessionId,
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

function updateSettingsSaveState() {
  elements.saveStorySettingsButton.disabled = state.savingSettings || !state.storyId;
}

function setSettingsSaveStatus(text, isError = false) {
  elements.settingsSaveStatus.textContent = text;
  elements.settingsSaveStatus.classList.toggle("error", Boolean(isError));
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

function makeEmptyListNode(text) {
  const node = document.createElement("div");
  node.className = "library-empty";
  node.textContent = text;
  return node;
}

function renderStoryState(storyState, version) {
  state.storyState = storyState;
  state.storyStateVersion = version;

  if (!storyState) {
    elements.storyStatePanel.hidden = true;
    return;
  }

  elements.storyStatePanel.hidden = false;
  elements.stateScene.textContent = storyState.current_scene || "未知";
  elements.stateStage.textContent = storyState.story_stage || "opening";

  const pendingEvents = Array.isArray(storyState.pending_events) ? storyState.pending_events.filter(Boolean) : [];
  if (pendingEvents.length) {
    elements.stateEvents.hidden = false;
    elements.stateEvents.replaceChildren(
      ...pendingEvents.slice(-3).map((eventText) => {
        const node = document.createElement("span");
        node.textContent = eventText;
        return node;
      }),
    );
  } else {
    elements.stateEvents.hidden = true;
    elements.stateEvents.replaceChildren();
  }

  const summary = typeof storyState.long_summary === "string" ? storyState.long_summary.trim() : "";
  elements.stateSummary.textContent = summary ? trimText(summary, 140) : `状态版本 ${version}`;
}

function trimText(value, maxLength) {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(-maxLength).replace(/^\S{0,12}/, "").trim()}...`;
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
        user_id: state.userId,
        session_id: state.sessionId,
        story_id: state.storyId,
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
    if (result.state_update) {
      await loadStoryState();
    }
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
    if (!state.sending) {
      void loadStoryState();
    }
  }
}

async function createStory() {
  const title = window.prompt("故事标题", elements.storyTitle.value.trim() || "新的故事");
  if (!title) {
    return;
  }

  const response = await fetch(`${API_BASE}/api/stories`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: state.userId,
      title,
      world_setting: elements.worldSetting.value.trim(),
      character_setting: elements.characterSetting.value.trim(),
      default_model: state.model,
    }),
  });
  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.message || "创建故事失败");
  }

  state.storyId = result.story.id;
  elements.storyTitle.value = result.story.title;
  elements.storyTitleDisplay.textContent = result.story.title;
  await createSession("新的会话", result.story.id);
  await loadLibrary();
  saveState();
}

async function createSession(title = "新的会话", storyId = state.storyId) {
  const response = await fetch(`${API_BASE}/api/stories/${encodeURIComponent(storyId)}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: state.userId,
      title,
    }),
  });
  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.message || "创建会话失败");
  }

  state.storyId = storyId;
  state.sessionId = result.session.id;
  state.messages = [];
  renderMessages();
  await loadSessions();
  await loadStoryState();
  saveState();
}

async function selectStory(storyId) {
  const story = state.stories.find((item) => item.id === storyId);
  state.storyId = storyId;
  if (story) {
    elements.storyTitle.value = story.title || "未命名故事";
    elements.storyTitleDisplay.textContent = elements.storyTitle.value;
    elements.worldSetting.value = story.world_setting || elements.worldSetting.value;
    elements.characterSetting.value = story.character_setting || elements.characterSetting.value;
  }
  await loadSessions();
  const firstSession = state.sessions[0];
  if (firstSession) {
    await selectSession(firstSession.id);
  } else {
    state.messages = [];
    renderMessages();
    renderStoryState(null, 0);
  }
  renderStories();
  setSettingsSaveStatus("");
  saveState();
}

async function selectSession(sessionId) {
  state.sessionId = sessionId;
  state.messages = [];
  renderMessages();
  await loadSessionMessages();
  await loadStoryState();
  renderSessions();
  saveState();
}

async function renameSession(sessionId) {
  const session = state.sessions.find((item) => item.id === sessionId);
  const title = window.prompt("会话名称", session?.title || "新的会话");
  if (!title) {
    return;
  }

  const response = await fetch(`${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.message || "重命名失败");
  }
  await loadSessions();
}

async function deleteSession(sessionId) {
  if (!window.confirm("删除这个会话？")) {
    return;
  }

  const response = await fetch(`${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.message || "删除失败");
  }

  await loadSessions();
  if (state.sessionId === sessionId) {
    const next = state.sessions[0];
    if (next) {
      await selectSession(next.id);
    } else {
      state.messages = [];
      renderMessages();
      renderStoryState(null, 0);
    }
  }
}

function renderStories() {
  elements.storyList.replaceChildren();

  if (!state.stories.length) {
    elements.storyList.append(makeEmptyListNode("暂无故事"));
    return;
  }

  for (const story of state.stories) {
    const row = document.createElement("div");
    row.className = story.id === state.storyId ? "story-row active" : "story-row";

    const select = document.createElement("button");
    select.type = "button";
    select.className = "library-item";
    select.dataset.storyId = story.id;
    select.innerHTML = `<strong></strong><span></span>`;
    select.querySelector("strong").textContent = story.title || "未命名故事";
    select.querySelector("span").textContent = `${story.session_count || 0} 个会话`;

    const rename = document.createElement("button");
    rename.type = "button";
    rename.className = "mini-button";
    rename.dataset.renameStoryId = story.id;
    rename.textContent = "改名";

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "mini-button danger";
    remove.dataset.deleteStoryId = story.id;
    remove.textContent = "删除";

    row.append(select, rename, remove);
    elements.storyList.append(row);
  }
}

function renderSessions() {
  elements.sessionList.replaceChildren();

  if (!state.sessions.length) {
    elements.sessionList.append(makeEmptyListNode("暂无会话"));
    return;
  }

  for (const session of state.sessions) {
    const row = document.createElement("div");
    row.className = session.id === state.sessionId ? "session-row active" : "session-row";

    const select = document.createElement("button");
    select.type = "button";
    select.className = "library-item";
    select.dataset.sessionId = session.id;
    select.innerHTML = `<strong></strong><span></span>`;
    select.querySelector("strong").textContent = session.title || "未命名会话";
    select.querySelector("span").textContent = `${session.message_count || 0} 条消息`;

    const rename = document.createElement("button");
    rename.type = "button";
    rename.className = "mini-button";
    rename.dataset.renameSessionId = session.id;
    rename.textContent = "改名";

    const clear = document.createElement("button");
    clear.type = "button";
    clear.className = "mini-button";
    clear.dataset.clearSessionId = session.id;
    clear.textContent = "清空";

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "mini-button danger";
    remove.dataset.deleteSessionId = session.id;
    remove.textContent = "删除";

    row.append(select, rename, clear, remove);
    elements.sessionList.append(row);
  }
}

async function renameStory(storyId) {
  const story = state.stories.find((item) => item.id === storyId);
  const title = window.prompt("故事名称", story?.title || "新的故事");
  if (!title) {
    return;
  }

  const response = await fetch(`${API_BASE}/api/stories/${encodeURIComponent(storyId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: state.userId,
      title,
    }),
  });
  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.message || "故事重命名失败");
  }

  if (state.storyId === storyId) {
    elements.storyTitle.value = result.story.title;
    elements.storyTitleDisplay.textContent = result.story.title;
  }
  await loadStories();
  setSettingsSaveStatus("");
  saveState();
}

async function saveStorySettings() {
  const title = elements.storyTitle.value.trim() || "未命名故事";
  state.savingSettings = true;
  updateSettingsSaveState();
  setSettingsSaveStatus("保存中...");

  try {
    const response = await fetch(`${API_BASE}/api/stories/${encodeURIComponent(state.storyId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: state.userId,
        title,
        world_setting: elements.worldSetting.value.trim(),
        character_setting: elements.characterSetting.value.trim(),
        default_model: state.model,
      }),
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.message || "保存设定失败");
    }

    const story = result.story;
    state.stories = state.stories.map((item) => (item.id === story.id ? { ...item, ...story } : item));
    if (!state.stories.some((item) => item.id === story.id)) {
      state.stories.unshift(story);
    }
    elements.storyTitle.value = story.title || title;
    elements.storyTitleDisplay.textContent = elements.storyTitle.value;
    elements.worldSetting.value = story.world_setting || "";
    elements.characterSetting.value = story.character_setting || "";
    renderStories();
    saveState();
    setSettingsSaveStatus("已保存");
  } catch (error) {
    setSettingsSaveStatus(error.message, true);
    throw error;
  } finally {
    state.savingSettings = false;
    updateSettingsSaveState();
  }
}

async function deleteStory(storyId) {
  const story = state.stories.find((item) => item.id === storyId);
  const title = story?.title || "这个故事";
  if (!window.confirm(`删除「${title}」？该故事下的会话、消息和状态会一并删除。`)) {
    return;
  }

  const response = await fetch(
    `${API_BASE}/api/stories/${encodeURIComponent(storyId)}?user_id=${encodeURIComponent(state.userId)}`,
    { method: "DELETE" },
  );
  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.message || "删除故事失败");
  }

  await loadStories();
  if (state.storyId !== storyId) {
    renderStories();
    saveState();
    return;
  }

  const nextStory = state.stories[0];
  if (nextStory) {
    await selectStory(nextStory.id);
  } else {
    state.storyId = DEFAULT_STORY_ID;
    state.sessionId = DEFAULT_SESSION_ID;
    state.sessions = [];
    state.messages = [];
    renderStories();
    renderSessions();
    renderMessages();
    renderStoryState(null, 0);
    saveState();
  }
}

async function clearSession(sessionId) {
  if (!window.confirm("清空这个会话的消息和故事状态？")) {
    return;
  }

  const response = await fetch(`${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}/messages`, {
    method: "DELETE",
  });
  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.message || "清空会话失败");
  }

  await loadSessions();
  if (state.sessionId === sessionId) {
    state.messages = [];
    renderMessages();
    renderStoryState(null, 0);
    saveState();
  }
}

function bindStoryManagementEvents() {
  elements.storyList.addEventListener("click", (event) => {
    const renameButton = event.target.closest("[data-rename-story-id]");
    const deleteButton = event.target.closest("[data-delete-story-id]");

    if (renameButton) {
      renameStory(renameButton.dataset.renameStoryId).catch((error) => {
        window.alert(error.message);
      });
      event.stopImmediatePropagation();
      return;
    }

    if (deleteButton) {
      deleteStory(deleteButton.dataset.deleteStoryId).catch((error) => {
        window.alert(error.message);
      });
      event.stopImmediatePropagation();
    }
  });

  elements.sessionList.addEventListener("click", (event) => {
    const clearButton = event.target.closest("[data-clear-session-id]");
    if (!clearButton) {
      return;
    }

    clearSession(clearButton.dataset.clearSessionId).catch((error) => {
      window.alert(error.message);
    });
    event.stopImmediatePropagation();
  });
}

function bindEvents() {
  elements.libraryToggle.addEventListener("click", () => {
    elements.libraryPanel.hidden = !elements.libraryPanel.hidden;
    if (!elements.libraryPanel.hidden) {
      void loadLibrary();
    }
  });

  elements.settingsToggle.addEventListener("click", () => {
    elements.settingsPanel.hidden = !elements.settingsPanel.hidden;
  });

  elements.newStoryButton.addEventListener("click", () => {
    createStory().catch((error) => {
      window.alert(error.message);
    });
  });

  elements.newSessionButton.addEventListener("click", () => {
    createSession().catch((error) => {
      window.alert(error.message);
    });
  });

  elements.storyList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-story-id]");
    if (!button) {
      return;
    }
    selectStory(button.dataset.storyId).catch((error) => {
      window.alert(error.message);
    });
  });

  elements.sessionList.addEventListener("click", (event) => {
    const selectButton = event.target.closest("[data-session-id]");
    const renameButton = event.target.closest("[data-rename-session-id]");
    const deleteButton = event.target.closest("[data-delete-session-id]");

    if (selectButton) {
      selectSession(selectButton.dataset.sessionId).catch((error) => {
        window.alert(error.message);
      });
      return;
    }
    if (renameButton) {
      renameSession(renameButton.dataset.renameSessionId).catch((error) => {
        window.alert(error.message);
      });
      return;
    }
    if (deleteButton) {
      deleteSession(deleteButton.dataset.deleteSessionId).catch((error) => {
        window.alert(error.message);
      });
    }
  });

  elements.modelSelect.addEventListener("change", () => {
    state.model = elements.modelSelect.value;
    setSettingsSaveStatus("未保存");
    saveState();
  });

  elements.storyTitle.addEventListener("input", () => {
    elements.storyTitleDisplay.textContent = elements.storyTitle.value.trim() || "未命名故事";
    setSettingsSaveStatus("未保存");
    saveState();
  });

  for (const input of [elements.worldSetting, elements.characterSetting]) {
    input.addEventListener("input", () => {
      setSettingsSaveStatus("未保存");
      saveState();
    });
  }

  elements.saveStorySettingsButton.addEventListener("click", () => {
    saveStorySettings().catch((error) => {
      window.alert(error.message);
    });
  });

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
  bindStoryManagementEvents();
  renderMessages();
  updateSendState();
  updateSettingsSaveState();
  refreshHealth();
  loadLibrary();
  loadSessionMessages();
  loadStoryState();
  window.setInterval(refreshHealth, 10000);
}

init();
