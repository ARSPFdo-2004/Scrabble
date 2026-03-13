/**
 * app.js – Live Score web app
 *
 * Connects to the Flask-SocketIO backend and keeps the UI in sync with
 * the game state in real time.
 */

/* ── Socket.IO connection ───────────────────────────────── */
const socket = io({ transports: ['websocket', 'polling'] });

const el = id => document.getElementById(id);

// Board layout labels (must match backend constants.py)
const BOARD_LAYOUT = [
  ['TW','','','DL','','','','TW','','','','DL','','','TW'],
  ['','DW','','','','TL','','','','TL','','','','DW',''],
  ['','','DW','','','','DL','','DL','','','','DW','',''],
  ['DL','','','DW','','','','DL','','','','DW','','','DL'],
  ['','','','','DW','','','','','','DW','','','',''],
  ['','TL','','','','TL','','','','TL','','','','TL',''],
  ['','','DL','','','','DL','','DL','','','','DL','',''],
  ['TW','','','DL','','','','DW','','','','DL','','','TW'],
  ['','','DL','','','','DL','','DL','','','','DL','',''],
  ['','TL','','','','TL','','','','TL','','','','TL',''],
  ['','','','','DW','','','','','','DW','','','',''],
  ['DL','','','DW','','','','DL','','','','DW','','','DL'],
  ['','','DW','','','','DL','','DL','','','','DW','',''],
  ['','DW','','','','TL','','','','TL','','','','DW',''],
  ['TW','','','DL','','','','TW','','','','DL','','','TW'],
];

const MULTIPLIER_LABELS = { TW: 'TW', DW: 'DW', TL: 'TL', DL: 'DL' };

let currentState   = null;
let selectedWord   = null;
let prevBoard      = null;
let exchangeSelected = new Map();

/* ── Build board DOM (once) ─────────────────────────────── */
function buildBoard() {
  const boardEl = el('board');
  boardEl.innerHTML = '';
  for (let r = 0; r < 15; r++) {
    for (let c = 0; c < 15; c++) {
      const cell = document.createElement('div');
      cell.classList.add('cell');
      cell.id = `cell-${r}-${c}`;
      const sq = BOARD_LAYOUT[r][c];
      if (r === 7 && c === 7) {
        cell.classList.add('CENTER');
        cell.textContent = '★';
      } else if (sq) {
        cell.classList.add(sq);
        cell.textContent = MULTIPLIER_LABELS[sq] || '';
      } else {
        cell.classList.add('empty');
      }
      boardEl.appendChild(cell);
    }
  }
}

/* ── Update board from state ────────────────────────────── */
function updateBoard(board, lastTiles) {
  const newTileSet = new Set(
    (lastTiles || []).map(([r, c]) => `${r}-${c}`)
  );

  for (let r = 0; r < 15; r++) {
    for (let c = 0; c < 15; c++) {
      const cell = el(`cell-${r}-${c}`);
      const letter = board[r][c];
      if (letter) {
        cell.textContent = letter;
        cell.classList.remove('TW','DW','TL','DL','CENTER','empty');
        cell.classList.add('occupied');
        if (newTileSet.has(`${r}-${c}`)) {
          cell.classList.add('new-tile');
          setTimeout(() => cell.classList.remove('new-tile'), 1200);
        }
      } else {
        // restore to original multiplier (works whether cell was occupied or not)
        cell.classList.remove('occupied','new-tile');
        const sq = BOARD_LAYOUT[r][c];
        cell.textContent = '';
        if (r === 7 && c === 7) {
          cell.classList.add('CENTER');
          cell.textContent = '★';
        } else if (sq) {
          cell.classList.add(sq);
          cell.textContent = MULTIPLIER_LABELS[sq] || '';
        } else {
          cell.classList.add('empty');
        }
      }
    }
  }
}

/* ── Render rack tiles ──────────────────────────────────── */
function renderRack(containerId, tiles) {
  const container = el(containerId);
  container.innerHTML = '';
  (tiles || []).forEach(letter => {
    const t = document.createElement('span');
    t.classList.add('tile');
    t.textContent = letter === '?' ? '?' : letter;
    container.appendChild(t);
  });
}

/* ── Render move history ────────────────────────────────── */
function renderHistory(history) {
  const tbody = el('historyBody');
  tbody.innerHTML = '';
  (history || []).forEach((move, idx) => {
    const tr = document.createElement('tr');
    const playerClass = move.player === 'human' ? 'player-human' : 'player-ai';
    const playerLabel = move.player === 'human' ? '👤 Human' : '🤖 AI';
    let wordsText, scoreText;
    if (move.action === 'pass') {
      wordsText = '<em>Pass</em>';
      scoreText = '—';
    } else if (move.action === 'exchange') {
      wordsText = '<em>Exchange</em>';
      scoreText = '—';
    } else if (move.action === 'challenge_failed') {
      wordsText = `<em>Challenge "${move.word}" failed</em>`;
      scoreText = '—';
    } else if (move.action === 'challenge_succeeded') {
      wordsText = `<em>Challenge "${move.word}" succeeded</em>`;
      scoreText = `+${move.points_awarded || 0}`;
    } else {
      wordsText = (move.words || []).join(', ');
      scoreText = `+${move.score || 0}`;
    }
    tr.innerHTML = `
      <td>${idx + 1}</td>
      <td class="${playerClass}">${playerLabel}</td>
      <td>${wordsText}</td>
      <td>${scoreText}</td>
      <td>${(move.scores || {}).human ?? ''}</td>
      <td>${(move.scores || {}).ai ?? ''}</td>
    `;
    tbody.appendChild(tr);
  });
}

/* ── Update challengeable words ─────────────────────────── */
function updateChallengeableWords(state) {
  const container = el('challengeableWords');
  container.innerHTML = '';
  const lastWord = state.last_placed_word;
  if (!lastWord || state.current_player !== 'human') return;

  const chip = document.createElement('span');
  chip.classList.add('word-chip');
  chip.textContent = lastWord;
  chip.onclick = () => {
    document.querySelectorAll('.word-chip').forEach(c => c.classList.remove('selected'));
    chip.classList.add('selected');
    el('challengeInput').value = lastWord;
    selectedWord = lastWord;
  };
  container.appendChild(chip);
}

/* ── Apply full game state ──────────────────────────────── */
function applyState(state) {
  currentState = state;

  // Scores
  el('humanScore').textContent = state.scores.human;
  el('aiScore').textContent    = state.scores.ai;

  // Active player highlight
  el('humanScoreCard').classList.toggle('active', state.current_player === 'human');
  el('aiScoreCard').classList.toggle('active',    state.current_player === 'ai');

  // Racks
  renderRack('humanRack', state.racks.human);
  renderRack('aiRack', Array.isArray(state.racks.ai)
    ? state.racks.ai
    : state.racks.ai.split('').map(() => '?'));

  // Turn
  const turnText = state.game_over
    ? 'Game Over'
    : (state.current_player === 'human' ? '👤 Your turn' : '🤖 AI is thinking…');
  el('currentTurn').textContent = turnText;
  el('tilesRemaining').textContent = `Tiles in bag: ${state.tiles_remaining}`;

  // Board
  const newTiles = state.last_placed_tiles || [];
  updateBoard(state.board, newTiles);

  // History
  renderHistory(state.move_history);

  // Challenge words
  updateChallengeableWords(state);

  // Exchange rack
  renderExchangeRack(state.racks.human);

  // Game over
  if (state.game_over) {
    const humanScore = state.scores.human;
    const aiScore    = state.scores.ai;
    let msg = '';
    if (humanScore > aiScore) msg = `🎉 Human wins! (${humanScore} vs ${aiScore})`;
    else if (aiScore > humanScore) msg = `🤖 AI wins! (${aiScore} vs ${humanScore})`;
    else msg = `🤝 It's a tie! (${humanScore} each)`;
    el('gameOverMessage').textContent = msg;
    el('gameOverOverlay').style.display = 'flex';
  } else {
    el('gameOverOverlay').style.display = 'none';
  }
}

/* ── Socket events ──────────────────────────────────────── */
socket.on('connect', () => {
  el('connectionStatus').textContent = 'Connected';
  el('connectionStatus').classList.add('connected');
});

socket.on('disconnect', () => {
  el('connectionStatus').textContent = 'Disconnected';
  el('connectionStatus').classList.remove('connected');
});

socket.on('game_state', applyState);

socket.on('place_result', result => {
  if (!result.success) {
    alert(`Move failed: ${result.error}`);
  }
});

socket.on('challenge_result', result => {
  const msgEl  = el('challengeResult');
  const valid  = result.valid;
  msgEl.textContent = result.message;
  msgEl.className   = 'challenge-result ' + (valid ? 'fail' : 'success');
  setTimeout(() => { msgEl.textContent = ''; }, 5000);
});

socket.on('navigate', data => {
  // Mirror hardware navigation in the UI (optional)
  console.log('Navigate event:', data);
});

socket.on('tile_cart_status', data => {
  console.log('Tile cart:', data);
});

/* ── Exchange rack (click-to-select) ────────────────────── */
function renderExchangeRack(tiles) {
  const container = el('exchangeRack');
  container.innerHTML = '';
  exchangeSelected = new Map();  // index → letter
  (tiles || []).forEach((letter, idx) => {
    const t = document.createElement('span');
    t.classList.add('tile', 'exchange-tile');
    t.textContent = letter === ' ' ? '?' : letter;
    t.dataset.index = idx;
    t.onclick = () => {
      t.classList.toggle('selected');
      if (t.classList.contains('selected')) {
        exchangeSelected.set(idx, letter);
      } else {
        exchangeSelected.delete(idx);
      }
    };
    container.appendChild(t);
  });
}

/* ── User actions ───────────────────────────────────────── */
function placeTiles() {
  const text  = el('tilesInput').value.trim();
  if (!text) return;
  const tiles = text.split('\n').map(line => {
    const parts = line.trim().split(',');
    if (parts.length < 3) return null;
    return [parseInt(parts[0]), parseInt(parts[1]), parts[2].trim().toUpperCase()];
  }).filter(Boolean);

  if (!tiles.length) { alert('No valid tile entries found.'); return; }
  socket.emit('place_tiles', { tiles });
  el('tilesInput').value = '';
}

function passTurn() {
  fetch('/api/pass', { method: 'POST' })
    .then(r => r.json())
    .then(result => { if (!result.success) alert(result.error); });
}

function exchangeTiles() {
  if (!exchangeSelected.size) { alert('Select tiles to exchange first.'); return; }
  fetch('/api/exchange', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ letters: Array.from(exchangeSelected.values()) }),
  })
    .then(r => r.json())
    .then(result => {
      if (!result.success) alert('Exchange failed: ' + result.error);
      else fetch('/api/state').then(r => r.json()).then(applyState).catch(() => {});
    });
}

function challengeWord() {
  const word = el('challengeInput').value.trim().toUpperCase();
  if (!word) { alert('Enter a word to challenge.'); return; }
  socket.emit('challenge', { word });
  el('challengeInput').value = '';
  document.querySelectorAll('.word-chip').forEach(c => c.classList.remove('selected'));
}

function newGame() {
  if (!confirm('Start a new game?')) return;
  fetch('/api/new_game', { method: 'POST' })
    .then(r => r.json())
    .then(() => { el('gameOverOverlay').style.display = 'none'; });
}

function scanBoard() {
  fetch('/api/scan_board', { method: 'POST' })
    .then(r => r.json())
    .then(result => {
      if (result.success) alert('Board scanned successfully.');
      else alert('Scan failed: ' + result.error);
    });
}

/* ── Init ───────────────────────────────────────────────── */
buildBoard();

// Also fetch initial state via REST in case SocketIO is slow
fetch('/api/state').then(r => r.json()).then(applyState).catch(() => {});
