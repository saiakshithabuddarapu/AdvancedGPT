let activeSessionId = null;
let currentStrategy = "";

document.addEventListener("DOMContentLoaded", () => {
  initApp();
});

function initApp() {
  setupEventListeners();
  loadSessions();
  loadDocuments();
  fetchRlStats();
}

function setupEventListeners() {
  // Sidebar toggle
  document.getElementById("sidebarToggle").addEventListener("click", () => {
    document.getElementById("sidebar").classList.toggle("collapsed");
  });

  // New Chat
  document.getElementById("newChatBtn").addEventListener("click", () => {
    createNewSession();
  });

  // Strategy Selector
  document.getElementById("actionStrategy").addEventListener("change", (e) => {
    currentStrategy = e.target.value;
  });

  // RL Drawer toggle
  document.getElementById("toggleRlDashboard").addEventListener("click", () => {
    openRlDrawer();
  });
  document.getElementById("closeRlDrawer").addEventListener("click", () => {
    closeRlDrawer();
  });
  document.getElementById("rlDrawerOverlay").addEventListener("click", () => {
    closeRlDrawer();
  });

  // Send message
  const chatInput = document.getElementById("chatInput");
  const sendBtn = document.getElementById("sendBtn");

  sendBtn.addEventListener("click", () => {
    sendMessage();
  });

  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Auto expand textarea
  chatInput.addEventListener("input", () => {
    chatInput.style.height = "auto";
    chatInput.style.height = Math.min(chatInput.scrollHeight, 150) + "px";
  });

  // File Upload
  const fileInput = document.getElementById("fileInput");
  const dropzone = document.getElementById("uploadDropzone");

  dropzone.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", (e) => {
    if (e.target.files.length > 0) {
      uploadFile(e.target.files[0]);
    }
  });

  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.style.borderColor = "var(--accent-teal)";
  });
  dropzone.addEventListener("dragleave", () => {
    dropzone.style.borderColor = "var(--border-color)";
  });
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.style.borderColor = "var(--border-color)";
    if (e.dataTransfer.files.length > 0) {
      uploadFile(e.dataTransfer.files[0]);
    }
  });
}

// Session Operations
async function loadSessions() {
  try {
    const res = await fetch("/api/sessions");
    const sessions = await res.json();
    
    const sessionList = document.getElementById("sessionList");
    sessionList.innerHTML = "";

    if (sessions.length > 0) {
      sessions.forEach(sess => {
        const item = document.createElement("div");
        item.className = `session-item ${sess.id === activeSessionId ? 'active' : ''}`;
        item.innerHTML = `
          <span class="title">${escapeHtml(sess.title)}</span>
          <i class="fa-solid fa-trash del-btn" title="Delete session" onclick="deleteSession(event, '${sess.id}')"></i>
        `;
        item.addEventListener("click", () => selectSession(sess.id));
        sessionList.appendChild(item);
      });

      if (!activeSessionId) {
        selectSession(sessions[0].id);
      }
    } else {
      createNewSession();
    }
  } catch (err) {
    console.error("Error loading sessions:", err);
  }
}

async function createNewSession() {
  try {
    const res = await fetch("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "New Chat" })
    });
    const newSess = await res.json();
    await loadSessions();
    selectSession(newSess.id);
  } catch (err) {
    console.error("Error creating session:", err);
  }
}

async function selectSession(sessionId) {
  activeSessionId = sessionId;
  await loadSessions(); // Re-render active state
  loadMessages(sessionId);
}

async function deleteSession(event, sessionId) {
  event.stopPropagation();
  if (!confirm("Are you sure you want to delete this chat session?")) return;

  try {
    await fetch(`/api/sessions/${sessionId}`, { method: "DELETE" });
    if (activeSessionId === sessionId) {
      activeSessionId = null;
    }
    loadSessions();
  } catch (err) {
    console.error("Error deleting session:", err);
  }
}

// Message Operations
async function loadMessages(sessionId) {
  const feed = document.getElementById("messageFeed");
  const hero = document.getElementById("heroWelcome");
  feed.innerHTML = "";

  try {
    const res = await fetch(`/api/sessions/${sessionId}/messages`);
    const messages = await res.json();

    if (messages.length === 0) {
      hero.style.display = "block";
      feed.style.display = "none";
    } else {
      hero.style.display = "none";
      feed.style.display = "flex";
      messages.forEach(msg => appendMessageUI(msg));
      scrollToBottom();
    }
  } catch (err) {
    console.error("Error loading messages:", err);
  }
}

async function sendMessage() {
  const input = document.getElementById("chatInput");
  const text = input.value.trim();
  if (!text) return;

  input.value = "";
  input.style.height = "auto";

  const hero = document.getElementById("heroWelcome");
  const feed = document.getElementById("messageFeed");
  hero.style.display = "none";
  feed.style.display = "flex";

  // Append user message UI immediately
  const userMsg = {
    role: "user",
    content: text
  };
  appendMessageUI(userMsg);
  scrollToBottom();

  // Typing indicator
  const typingId = appendTypingIndicator();
  scrollToBottom();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: activeSessionId,
        message: text,
        manual_action: currentStrategy || null
      })
    });

    removeTypingIndicator(typingId);

    if (!res.ok) {
      throw new Error("Chat response failed");
    }

    const data = await res.json();
    appendMessageUI(data.message, data);
    scrollToBottom();
    
    // Refresh sessions title & RL stats
    loadSessions();
    fetchRlStats();

  } catch (err) {
    removeTypingIndicator(typingId);
    appendMessageUI({
      role: "assistant",
      content: "⚠️ Sorry, an error occurred while generating response."
    });
    console.error("Send message error:", err);
  }
}

function sendSuggested(promptText) {
  document.getElementById("chatInput").value = promptText;
  sendMessage();
}

function appendMessageUI(msg, apiMetaData = null) {
  const feed = document.getElementById("messageFeed");
  const row = document.createElement("div");
  row.className = `msg-row ${msg.role}`;

  const avatarIcon = msg.role === "user" ? '<i class="fa-solid fa-user"></i>' : '<i class="fa-solid fa-robot"></i>';

  let badgesHtml = "";
  if (msg.role === "assistant") {
    const tools = msg.tools_used || (apiMetaData ? apiMetaData.tools_used : []);
    const action = msg.action_selected || (apiMetaData ? apiMetaData.action_selected : null);
    
    badgesHtml += '<div class="badges-container">';
    if (action) {
      badgesHtml += `<span class="badge badge-rl"><i class="fa-solid fa-brain"></i> Strategy: ${escapeHtml(action)}</span>`;
    }
    if (tools && tools.length > 0) {
      tools.forEach(t => {
        const icon = t.includes("Web") ? "fa-globe" : "fa-file-contract";
        badgesHtml += `<span class="badge badge-tool"><i class="fa-solid ${icon}"></i> ${escapeHtml(t)}</span>`;
      });
    }
    badgesHtml += '</div>';
  }

  // Markdown rendering
  const formattedContent = marked.parse(msg.content);

  let feedbackHtml = "";
  if (msg.role === "assistant" && msg.id) {
    const isUp = msg.feedback === 1 ? "active-up" : "";
    const isDown = msg.feedback === -1 ? "active-down" : "";
    feedbackHtml = `
      <div class="msg-feedback">
        <span>Helpful?</span>
        <button class="fb-btn ${isUp}" onclick="submitFeedback('${msg.id}', 1, this)">
          <i class="fa-solid fa-thumbs-up"></i>
        </button>
        <button class="fb-btn ${isDown}" onclick="submitFeedback('${msg.id}', -1, this)">
          <i class="fa-solid fa-thumbs-down"></i>
        </button>
      </div>
    `;
  }

  row.innerHTML = `
    <div class="msg-avatar">${avatarIcon}</div>
    <div class="msg-content-wrapper">
      ${badgesHtml}
      <div class="msg-bubble">${formattedContent}</div>
      ${feedbackHtml}
    </div>
  `;

  feed.appendChild(row);
}

async function submitFeedback(msgId, feedbackVal, btnElement) {
  try {
    const res = await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message_id: msgId, feedback: feedbackVal })
    });
    
    const data = await res.json();
    if (data.status === "success") {
      // Highlight button
      const parent = btnElement.parentElement;
      parent.querySelectorAll(".fb-btn").forEach(b => b.classList.remove("active-up", "active-down"));
      if (feedbackVal === 1) btnElement.classList.add("active-up");
      if (feedbackVal === -1) btnElement.classList.add("active-down");

      // Update RL drawer stats
      updateRlDrawerUI(data.updated_rl_stats);
    }
  } catch (err) {
    console.error("Feedback submission error:", err);
  }
}

function appendTypingIndicator() {
  const feed = document.getElementById("messageFeed");
  const id = "typing_" + Date.now();
  const row = document.createElement("div");
  row.className = "msg-row assistant";
  row.id = id;
  row.innerHTML = `
    <div class="msg-avatar"><i class="fa-solid fa-robot"></i></div>
    <div class="msg-content-wrapper">
      <div class="msg-bubble"><i class="fa-solid fa-ellipsis fa-beat"></i> ChatGPT is processing tools & RL...</div>
    </div>
  `;
  feed.appendChild(row);
  return id;
}

function removeTypingIndicator(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

function scrollToBottom() {
  const container = document.getElementById("messagesContainer");
  container.scrollTop = container.scrollHeight;
}

// Document Operations
async function uploadFile(file) {
  const formData = new FormData();
  formData.append("file", file);

  const dropzone = document.getElementById("uploadDropzone");
  dropzone.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Ingesting ${escapeHtml(file.name)}...`;

  try {
    const res = await fetch("/api/rag/upload", {
      method: "POST",
      body: formData
    });
    const data = await res.json();
    
    dropzone.innerHTML = `<i class="fa-solid fa-cloud-arrow-up"></i> Upload PDF/TXT/MD/JSON`;
    loadDocuments();
    alert(`File "${file.name}" indexed successfully into RAG store! (${data.details.chunk_count} chunks created)`);
  } catch (err) {
    dropzone.innerHTML = `<i class="fa-solid fa-cloud-arrow-up"></i> Upload PDF/TXT/MD/JSON`;
    alert("Error uploading document: " + err);
  }
}

async function loadDocuments() {
  try {
    const res = await fetch("/api/rag/documents");
    const docs = await res.json();
    
    const docList = document.getElementById("docList");
    docList.innerHTML = "";

    if (docs.length === 0) {
      docList.innerHTML = '<div style="font-size:0.75rem; color:var(--text-muted);">No documents uploaded yet.</div>';
    } else {
      docs.forEach(d => {
        const item = document.createElement("div");
        item.className = "doc-item";
        item.innerHTML = `
          <span class="doc-name"><i class="fa-solid fa-file"></i> ${escapeHtml(d.filename)}</span>
          <span>${d.chunk_count} chunks</span>
        `;
        docList.appendChild(item);
      });
    }
  } catch (err) {
    console.error("Error loading documents:", err);
  }
}

// RL Drawer Operations
function openRlDrawer() {
  document.getElementById("rlDrawer").classList.add("active");
  document.getElementById("rlDrawerOverlay").classList.add("active");
  fetchRlStats();
}

function closeRlDrawer() {
  document.getElementById("rlDrawer").classList.remove("active");
  document.getElementById("rlDrawerOverlay").classList.remove("active");
}

async function fetchRlStats() {
  try {
    const res = await fetch("/api/rl/stats");
    const stats = await res.json();
    updateRlDrawerUI(stats);
  } catch (err) {
    console.error("Error fetching RL stats:", err);
  }
}

function updateRlDrawerUI(stats) {
  if (!stats) return;

  document.getElementById("statInteractions").textContent = stats.total_interactions;
  document.getElementById("statReward").textContent = stats.total_reward;
  
  const satisfaction = Math.round(((stats.average_reward + 1) / 2) * 100);
  document.getElementById("statAvgReward").textContent = satisfaction + "%";
  document.getElementById("statEpsilon").textContent = Math.round(stats.epsilon * 100) + "%";

  // Q-Value progress bars
  const qBarContainer = document.getElementById("qValueBars");
  qBarContainer.innerHTML = "";

  const qVals = stats.overall_q_values || {};
  Object.keys(qVals).forEach(action => {
    const val = qVals[action];
    // Map Q-value (-1 to 1) to percentage (0 to 100)
    const pct = Math.max(5, Math.min(100, Math.round(((val + 1) / 2) * 100)));
    
    const row = document.createElement("div");
    row.className = "q-bar-row";
    row.innerHTML = `
      <div class="q-bar-label">
        <span>${escapeHtml(action)}</span>
        <span>Q = ${val}</span>
      </div>
      <div class="q-bar-bg">
        <div class="q-bar-fill" style="width: ${pct}%"></div>
      </div>
    `;
    qBarContainer.appendChild(row);
  });

  // Action Count List
  const countContainer = document.getElementById("actionCountList");
  countContainer.innerHTML = "";
  const counts = stats.action_counts || {};
  Object.keys(counts).forEach(action => {
    const item = document.createElement("div");
    item.style.fontSize = "0.8rem";
    item.style.display = "flex";
    item.style.justifyContent = "space-between";
    item.style.marginBottom = "6px";
    item.innerHTML = `<span>${escapeHtml(action)}</span><b>${counts[action]} times</b>`;
    countContainer.appendChild(item);
  });

  // Reward History Log
  const logContainer = document.getElementById("rewardHistoryLog");
  logContainer.innerHTML = "";
  const history = stats.reward_history || [];

  if (history.length === 0) {
    logContainer.innerHTML = '<div style="font-size:0.75rem; color:var(--text-muted);">No user feedback updates recorded yet. Click 👍/👎 on any bot message!</div>';
  } else {
    history.slice().reverse().forEach(log => {
      const isPos = log.reward > 0;
      const logItem = document.createElement("div");
      logItem.className = `log-item ${isPos ? 'positive' : 'negative'}`;
      logItem.innerHTML = `
        <div>
          <b>${log.action}</b> (${log.state})<br>
          <span style="color:var(--text-muted)">Q: ${log.old_q} → ${log.new_q}</span>
        </div>
        <div>
          <b>${isPos ? '+1.0 👍' : '-1.0 👎'}</b>
        </div>
      `;
      logContainer.appendChild(logItem);
    });
  }
}

// Utility
function escapeHtml(text) {
  if (!text) return "";
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
