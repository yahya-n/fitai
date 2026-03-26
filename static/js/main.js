/* ========================================
   FITAI — MAIN JS
   Neo-Brutalist Sport · 2025
   ======================================== */

// ─── INIT: DYNAMIC TICKER & AVATAR ───
(function initDynamic() {
  // Populate ticker from store
  const tickerEl = document.getElementById('tickerInner');
  if (tickerEl && typeof FitStore !== 'undefined') {
    const items = FitStore.getTickerItems();
    // Duplicate for seamless scroll
    let html = '';
    for (let rep = 0; rep < 3; rep++) {
      items.forEach(text => {
        // Split into label and value parts
        const parts = text.split(/(\d[\d,.]*\s*\w*$)/);
        if (parts.length > 1) {
          html += `<span class="ticker-item">${parts[0]}<span>${parts[1]}</span> &nbsp;→&nbsp;</span>`;
        } else {
          html += `<span class="ticker-item">${text} &nbsp;→&nbsp;</span>`;
        }
      });
    }
    tickerEl.innerHTML = html;
  }

  // Populate avatar with user initials
  const avatarEl = document.getElementById('avatarBtn');
  if (avatarEl && typeof FitStore !== 'undefined') {
    const profile = FitStore.getProfile();
    const name = profile.name || 'Athlete';
    const parts = name.trim().split(/\s+/);
    const initials = parts.length >= 2
      ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
      : name.substring(0, 2).toUpperCase();
    avatarEl.textContent = initials;

    // Also populate user dropdown name
    const dropdownName = document.getElementById('userDropdownName');
    if (dropdownName) dropdownName.textContent = name.toUpperCase();
  }
})();

// ─── SIDEBAR ───
function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
}
document.addEventListener('click', e => {
  const sb = document.getElementById('sidebar');
  const tog = document.querySelector('.menu-toggle');
  if (sb && sb.classList.contains('open') && !sb.contains(e.target) && tog && !tog.contains(e.target)) {
    sb.classList.remove('open');
  }
});

// ─── CHAT ───
const chatHistory = [];

function openChat() {
  document.getElementById('chatPanel').classList.add('on');
  document.getElementById('chatBackdrop').classList.add('on');
  setTimeout(() => document.getElementById('chatInput')?.focus(), 300);
}
function closeChat() {
  document.getElementById('chatPanel').classList.remove('on');
  document.getElementById('chatBackdrop').classList.remove('on');
}

async function sendChat() {
  const input = document.getElementById('chatInput');
  const msg = input.value.trim();
  if (!msg) return;
  input.value = '';

  appendChat(msg, 'user');
  const thinking = appendChat('PROCESSING...', 'typing');
  chatHistory.push({ role: 'user', content: msg });

  try {
    // Include profile context for personalized responses
    const profile = typeof FitStore !== 'undefined' ? FitStore.getProfile() : {};
    const stats = typeof FitStore !== 'undefined' ? FitStore.getStats() : {};
    const contextMsg = `[User Context: ${profile.name || 'Athlete'}, ${profile.age}yo, ${profile.fitness_level}, Goal: ${profile.goal}, Weight: ${profile.weight}kg, Streak: ${stats.streak || 0} days, Total workouts: ${stats.totalWorkouts || 0}]\n\n${msg}`;

    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: contextMsg, history: chatHistory.slice(-12) })
    });
    if (res.status === 401) { window.location.href = '/login'; return; }
    const data = await res.json();
    thinking.remove();
    const reply = data.success ? data.response : 'Error: Check your API key.';
    appendChat(reply, 'ai');
    chatHistory.push({ role: 'assistant', content: reply });
  } catch (e) {
    thinking.remove();
    appendChat('Network error: ' + e.message, 'ai');
  }
}

function appendChat(text, role) {
  const wrap = document.getElementById('chatMsgs');
  const div = document.createElement('div');
  div.className = `msg msg-${role === 'user' ? 'user' : role === 'typing' ? 'typing' : 'ai'}`;
  div.innerHTML = `<div class="msg-bubble">${fmt(text)}</div>`;
  wrap.appendChild(div);
  wrap.scrollTop = wrap.scrollHeight;
  return div;
}

function fmt(t) {
  return t
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/\n/g, '<br>');
}

// ─── WORKOUT TIMER ───
let timerSecs = 0, timerRunning = false, timerInterval = null;

function startWorkout(label) {
  document.getElementById('timerModal').classList.add('on');
  document.getElementById('timerExercise').textContent = (label || 'SESSION ACTIVE').toUpperCase();
  timerSecs = 0; timerRunning = true;
  timerInterval = setInterval(tickTimer, 1000);
}

function tickTimer() {
  if (!timerRunning) return;
  timerSecs++;
  const m = String(Math.floor(timerSecs / 60)).padStart(2, '0');
  const s = String(timerSecs % 60).padStart(2, '0');
  document.getElementById('timerClock').textContent = m + ':' + s;
  const cal = Math.floor(timerSecs / 60 * 7);
  document.getElementById('timerCal').textContent = cal;
}

function togglePause() {
  timerRunning = !timerRunning;
  const btn = document.getElementById('timerPauseBtn');
  btn.innerHTML = timerRunning
    ? '<i class="fas fa-pause"></i> Pause'
    : '<i class="fas fa-play"></i> Resume';
}

function endWorkout() {
  clearInterval(timerInterval);
  document.getElementById('timerModal').classList.remove('on');
  const mins = Math.floor(timerSecs / 60);
  const cal = Math.floor(mins * 7);

  // Auto-log the workout to the store
  if (typeof FitStore !== 'undefined' && mins > 0) {
    const todayPlan = FitStore.getTodayWorkout();
    FitStore.addWorkout({
      type: todayPlan?.workout?.focus || 'General Workout',
      dur: mins,
      cal: cal,
      intensity: mins > 45 ? 'Hard' : 'Moderate',
      mood: '💪 Strong',
      notes: 'Timer session',
    });
  }

  showToast('success', `Workout complete! ${mins} min · ~${cal} cal 💪`);
  timerSecs = 0; timerRunning = false;
}

// ─── TOAST NOTIFICATION ───
function showToast(type, message) {
  const existing = document.getElementById('fitToast');
  if (existing) existing.remove();

  const colors = { success: 'var(--green)', error: 'var(--red)', info: 'var(--blue)', warning: 'var(--yellow)' };
  const icons = { success: 'fa-check-circle', error: 'fa-times-circle', info: 'fa-info-circle', warning: 'fa-exclamation-triangle' };

  const toast = document.createElement('div');
  toast.id = 'fitToast';
  toast.style.cssText = `
    position:fixed;bottom:1.5rem;right:1.5rem;z-index:9999;
    background:var(--black2);border:2px solid ${colors[type]||colors.info};
    padding:0.85rem 1.25rem;
    display:flex;align-items:center;gap:0.65rem;
    font-family:var(--font-cond);font-size:0.9rem;font-weight:700;letter-spacing:1px;
    color:${colors[type]||colors.info};
    max-width:340px;
    animation:slideUp 0.25s ease both;
    box-shadow:4px 4px 0 ${colors[type]||colors.info};
  `;
  toast.innerHTML = `<i class="fas ${icons[type]||icons.info}"></i><span style="color:var(--white);font-weight:500;font-family:var(--font-body);font-size:0.875rem;">${message}</span>`;
  document.body.appendChild(toast);
  setTimeout(() => toast.style.opacity = '0', 3000);
  setTimeout(() => toast.remove(), 3300);
}

// ─── USER MENU ───
function toggleUserMenu() {
  const dd = document.getElementById('userDropdown');
  if (dd) dd.classList.toggle('show');
}

// Close dropdown when clicking outside
document.addEventListener('click', e => {
  const menu = document.querySelector('.user-menu');
  const dd = document.getElementById('userDropdown');
  if (dd && dd.classList.contains('show') && menu && !menu.contains(e.target)) {
    dd.classList.remove('show');
  }
});

async function doLogout() {
  try {
    await fetch('/auth/logout', { method: 'POST' });
  } catch(e) {}
  // Clear local store data
  Object.keys(localStorage).forEach(k => {
    if (k.startsWith('fitai_')) localStorage.removeItem(k);
  });
  window.location.href = '/login';
}

// expose globally
window.showToast = showToast;
window.startWorkout = startWorkout;
window.togglePause = togglePause;
window.endWorkout = endWorkout;
window.openChat = openChat;
window.closeChat = closeChat;
window.sendChat = sendChat;
window.toggleSidebar = toggleSidebar;
window.toggleUserMenu = toggleUserMenu;
window.doLogout = doLogout;
