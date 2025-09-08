# app.py
from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit, join_room
import random, time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

# In-memory session
# session_name -> {
#   'players': { sid: {'name','credit','wins','losses','point','joined_at'} },
#   'turn': sid,
#   'log': [ (ts, text) ... ],
#   'creator': sid
# }
sessions = {}

template = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Pop & Krepp Multiplayer Dice</title>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#e9f0f6;--card:#ffffff;--accent:#2196F3;--win:#28a745;--lose:#e55353}
body{font-family:Inter,Arial,Helvetica,sans-serif;background:var(--bg);margin:0;color:#222}
.header{display:flex;align-items:center;justify-content:space-between;padding:18px 28px;background:#fff;box-shadow:0 4px 14px rgba(0,0,0,0.06)}
.header h1{margin:0;font-size:18px}
.container{max-width:1100px;margin:20px auto;padding:16px}
.panel{background:var(--card);border-radius:12px;padding:14px;box-shadow:0 6px 20px rgba(16,24,40,0.06);margin-bottom:18px}
.row{display:flex;gap:12px;align-items:center}
.controls input[type="text"], .controls input[type="number"], .controls select{padding:8px 10px;border-radius:8px;border:1px solid #ddd}
.controls button{padding:8px 12px;border-radius:8px;border:none;background:var(--accent);color:white;cursor:pointer}
.controls button[disabled]{opacity:.5;cursor:default}
#board{height:320px;display:flex;flex-direction:column;align-items:center;justify-content:center}
.dice-row{display:flex;gap:28px;align-items:center}
.dice{width:120px;height:120px;background:#fff;border-radius:12px;display:flex;align-items:center;justify-content:center;font-weight:700;box-shadow:0 8px 30px rgba(2,6,23,0.08);position:relative;overflow:visible;transition:all 0.2s ease}
.dice .dots{position:relative;width:100%;height:100%}
.dot{position:absolute;border-radius:50%;background:#111}
.small{font-size:14px;color:#666}
.players-line{font-weight:600;margin-bottom:6px}
.turn-badge{display:inline-block;padding:6px 10px;border-radius:999px;background:linear-gradient(90deg,rgba(255,255,255,0.08),rgba(255,255,255,0.02));border:1px solid rgba(0,0,0,0.04)}
.stats-row{display:flex;gap:12px;flex-wrap:wrap}
.stat{background:#f7fafc;padding:8px 10px;border-radius:8px;font-size:13px}
#log{height:180px;overflow:auto;font-size:13px;padding:8px;background:#fff;border-radius:8px;border:1px solid #eee}
.controls .small{display:block;margin-top:6px;color:#666}
.popup{position:fixed;right:20px;bottom:20px;padding:18px;border-radius:12px;color:white;font-weight:700;box-shadow:0 10px 30px rgba(0,0,0,0.12);transform:translateY(40px);opacity:0;pointer-events:none;z-index:1000}
.popup.show{animation:pop 700ms forwards}
@keyframes pop{to{transform:translateY(0);opacity:1}}
.chart-wrap{height:160px;padding:8px;background:#fff;border-radius:8px}
.footer-small{font-size:12px;color:#666;margin-top:6px}
button:hover:not([disabled]){opacity:.85}
</style>
</head>
<body>
<header class="header">
  <h1>Pop & Krepp — Multiplayer</h1>
  <div style="font-size:13px;color:#666">Realtime | Session-based | Pop/Krepp rules</div>
</header>

<div class="container">
  <!-- Controls -->
  <div class="panel controls">
    <div class="row" style="justify-content:space-between">
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
        <input id="playerName" placeholder="Your name" type="text">
        <input id="sessionName" placeholder="Session name" type="text">
        <input id="startCredit" placeholder="Initial credit" type="number" value="10" min="1" style="width:160px">
        <button id="createBtn">Create Session</button>
        <button id="joinBtn">Request Join</button>
        <button id="startBtn">Start Game</button>
      </div>

      <div style="display:flex;gap:8px;align-items:center">
        <label class="small">Dice style</label>
        <select id="diceStyle"><option value="numbers">Numbers</option><option value="dots">Dots</option></select>
        <label class="small">Dice size</label>
        <input id="diceSize" type="range" min="50" max="160" value="120">
      </div>
    </div>
    <div class="footer-small">Set initial credit per player. Join requests require creator approval.</div>
  </div>

  <!-- Session info -->
  <div class="panel" id="sessionPanel">
    <div class="players-line" id="vsLine">No active session</div>
    <div class="row" style="justify-content:space-between">
      <div id="turnInfo" class="small">Not started</div>
      <div class="stats-row" id="miniStats"></div>
    </div>
  </div>

  <!-- Board -->
  <div class="panel" id="boardPanel">
    <div id="board">
      <div class="dice-row">
        <div id="dice1" class="dice"><div class="dots"></div></div>
        <div id="dice2" class="dice"><div class="dots"></div></div>
      </div>
      <div style="margin-top:14px;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
        <button id="rollBtn" disabled>Roll Dice</button>
        <button id="passBtn" disabled>Pass Dice</button>
        <button id="playAgainBtn" disabled>Play Again</button>
        <div id="winnerNote" style="color:var(--win);font-weight:700"></div>
      </div>
    </div>
  </div>

  <!-- Stats & logs -->
  <div style="display:flex;gap:12px;flex-wrap:wrap">
    <div style="flex:1;min-width:300px">
      <div class="panel">
        <div><strong>Players & Stats</strong></div>
        <div id="playersInfo" style="margin-top:10px"></div>
      </div>
      <div class="panel">
        <div><strong>Win/Loss Chart</strong></div>
        <div class="chart-wrap"><canvas id="winChart"></canvas></div>
      </div>
    </div>
    <div style="width:360px;min-width:300px">
      <div class="panel">
        <div><strong>Game Log</strong></div>
        <div id="log"></div>
      </div>
      <div class="panel">
        <div><strong>Pending Join Requests</strong></div>
        <div id="requests"></div>
      </div>
    </div>
  </div>
</div>

<!-- popup -->
<div id="popup" class="popup"></div>

<!-- libs -->
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
<script>
// FLASK SOCKET.IO MULTIPLAYER LOGIC
const socket = io();
let mySid = null, myName = null, currentSession = null;

const rollBtn = document.getElementById('rollBtn');
const passBtn = document.getElementById('passBtn');
const playAgainBtn = document.getElementById('playAgainBtn');
const createBtn = document.getElementById('createBtn');
const joinBtn = document.getElementById('joinBtn');
const startBtn = document.getElementById('startBtn');
const playerNameInput = document.getElementById('playerName');
const sessionNameInput = document.getElementById('sessionName');
const startCreditInput = document.getElementById('startCredit');
const playersInfoDiv = document.getElementById('playersInfo');
const vsLine = document.getElementById('vsLine');
const turnInfo = document.getElementById('turnInfo');
const logDiv = document.getElementById('log');
const requestsDiv = document.getElementById('requests');
const diceSize = document.getElementById('diceSize');
const diceStyle = document.getElementById('diceStyle');
const dice1 = document.getElementById('dice1');
const dice2 = document.getElementById('dice2');
const popup = document.getElementById('popup');
const winnerNote = document.getElementById('winnerNote');

const ctx = document.getElementById('winChart').getContext('2d');
let winChart = new Chart(ctx, {type:'line', data:{labels:[], datasets:[{label:'Wins',data:[],borderColor:'#28a745',tension:0.2,fill:false},{label:'Losses',data:[],borderColor:'#e55353',tension:0.2,fill:false}]}, options:{responsive:true,plugins:{legend:{position:'bottom'}}}});

function showPopup(text,color){
  popup.textContent=text;popup.style.background=color;popup.classList.remove('show');void popup.offsetWidth;popup.classList.add('show');
  setTimeout(()=>popup.classList.remove('show'),2400);
}
function addLog(text){const p=document.createElement('div');p.textContent=text;logDiv.prepend(p);}
function drawDotsContainer(container,n){
  const size=Number(diceSize.value);container.innerHTML='';
  const positions={1:[[50,50]],2:[[25,25],[75,75]],3:[[25,25],[50,50],[75,75]],4:[[25,25],[25,75],[75,25],[75,75]],5:[[25,25],[25,75],[50,50],[75,25],[75,75]],6:[[25,20],[25,50],[25,80],[75,20],[75,50],[75,80]]};
  positions[n].forEach(p=>{const d=document.createElement('div');d.className='dot';d.style.width=(size/6)+'px';d.style.height=(size/6)+'px';d.style.top=(p[1]/100*size-size/12)+'px';d.style.left=(p[0]/100*size-size/12)+'px';container.appendChild(d);});
}
function drawDiceElement(el,n){
  el.style.width=diceSize.value+'px';el.style.height=diceSize.value+'px';
  const inner=el.querySelector('.dots');
  if(diceStyle.value==='numbers'){inner.innerHTML='<div style="font-size:'+ (Number(diceSize.value)/2) +'px;">'+n+'</div>'} 
  else {drawDotsContainer(inner,n);}
}

// UI actions
createBtn.onclick=()=>{const name=playerNameInput.value.trim();const session=sessionNameInput.value.trim();const credit=parseInt(startCreditInput.value)||10;if(!name||!session){alert('Enter name and session');return;}myName=name;socket.emit('create_session',{session,name,initial_credit:credit});currentSession=session;}
joinBtn.onclick=()=>{const name=playerNameInput.value.trim();const session=sessionNameInput.value.trim();if(!name||!session){alert('Enter name and session');return;}myName=name;socket.emit('request_join',{session,name});currentSession=session;}
startBtn.onclick=()=>{if(!currentSession){alert('Enter or join a session first');return;}socket.emit('start_session',{session:currentSession});}
rollBtn.onclick=()=>{if(!currentSession)return;socket.emit('roll_request',{session:currentSession,name:myName});}
passBtn.onclick=()=>{if(!currentSession)return;socket.emit('pass_request',{session:currentSession,name:myName});}
playAgainBtn.onclick=()=>{if(!currentSession)return;socket.emit('play_again',{session:currentSession,name:myName});}

// dice slider redraw
diceSize.addEventListener('input',()=>{drawDiceElement(dice1,1);drawDiceElement(dice2,1);});

// initial dice
drawDiceElement(dice1,1);drawDiceElement(dice2,1);


</script>
</body>
</html>

"""

@app.route('/')
def index():
    return render_template_string(template)

# ---------------------------
# Helper utilities
# ---------------------------
def now_ts():
    return int(time.time())

def players_summary(players):
    # convert sessions[...]['players'] mapping to serializable list
    return { sid: {'name': p['name'], 'credit': p['credit'], 'wins': p['wins'], 'losses': p['losses'], 'point': p['point']} for sid, p in players.items() }

# ---------------------------
# Socket handlers
# ---------------------------

@socketio.on('create_session')
def on_create_session(data):
    session = data.get('session')
    name = data.get('name')
    initial_credit = int(data.get('initial_credit') or 10)
    sid = request.sid
    if not session or not name:
        emit('alert', 'Missing session or name', room=sid); return
    if session in sessions:
        emit('alert', 'Session already exists', room=sid); return
    sessions[session] = {
        'players': { sid: {'name': name, 'credit': initial_credit, 'wins':0, 'losses':0, 'point': None, 'joined_at': now_ts()} },
        'turn': sid,
        'log': [],
        'creator': sid
    }
    join_room(session)
    emit('session_created', {'session': session, 'creator': name, 'vs_list': name, 'players': players_summary(sessions[session]['players'])}, room=sid)







@socketio.on('request_join')
def on_request_join(data):
    session = data.get('session')
    name = data.get('name')
    sid = request.sid
    if not session or not name:
        emit('alert','Missing session or name', room=sid); return
    s = sessions.get(session)
    if not s:
        emit('alert','Session does not exist', room=sid); return
    # register as pending in s['requests'] (we'll reuse players map but mark as pending)
    # Add to players but mark credit=0 and wait for approval flag by storing 'approved' key.
    s['players'][sid] = {'name': name, 'credit': 0, 'wins':0, 'losses':0, 'point':None, 'joined_at': now_ts(), 'approved': False}
    join_room(session)
    # notify creator for approval
    creator_sid = s['creator']
    emit('join_request_received', {'session': session, 'sid': sid, 'name': name}, room=creator_sid)
    emit('alert', 'Join request sent. Waiting approval.', room=sid)

@socketio.on('approve_request')
def on_approve_request(data):
    session = data.get('session'); sid_to = data.get('sid'); ok = data.get('ok')
    sid = request.sid
    s = sessions.get(session)
    if not s: emit('alert','Session does not exist', room=sid); return
    if sid != s['creator']:
        emit('alert','Only creator can approve', room=sid); return
    player = s['players'].get(sid_to)
    if not player:
        emit('alert','Request not found', room=sid); return
    if not ok:
        # remove player
        del s['players'][sid_to]
        emit('approval_result', {'ok': False, 'msg': f"Rejected {player['name']}"}, room=session)
        return
    # approved: set credit to initial (copy from creator's starting credit if present), mark approved
    creator_credit = next(iter(s['players'].values()))['credit'] if s['players'] else 10
    player['credit'] = creator_credit
    player['approved'] = True
    emit('approval_result', {'ok': True, 'msg': f"Approved {player['name']}", 'players': players_summary(s['players'])}, room=session)

@socketio.on('start_session')
def on_start_session(data):
    session = data.get('session'); sid = request.sid
    s = sessions.get(session)
    if not s: emit('alert','Session does not exist', room=sid); return
    # require at least 2 approved players
    approved = [p for p in s['players'].items() if p[1].get('approved', True)]
    if len(approved) < 2:
        emit('alert','Need at least 2 players (approved)', room=sid); return
    # ensure turn is creator
    s['turn'] = s['creator']
    first = s['players'][s['turn']]['name']
    emit('game_started', {'turn': first, 'vs_list': " vs ".join([p['name'] for p in s['players'].values() if p.get('approved', True)]), 'players': players_summary(s['players'])}, room=session)

@socketio.on('roll_request')
def on_roll_request(data):
    session = data.get('session'); name = data.get('name'); sid = request.sid
    s = sessions.get(session)
    if not s: emit('alert','Session not found', room=sid); return
    if s['turn'] != sid:
        emit('alert','Not your turn', room=sid); return
    player = s['players'].get(sid)
    if not player or not player.get('approved', True):
        emit('alert','You are not approved to play', room=sid); return
    if player['credit'] <= 0:
        emit('alert','No credit left', room=sid); return
    # consume credit for the roll
    player['credit'] -= 1

    d1 = random.randint(1,6); d2 = random.randint(1,6); total = d1 + d2
    result = ''
    winner_sid = None

    # First roll or continuing (Mail)
    if player['point'] is None:
        if total in (7,11):
            result = 'Pop (Win)'
            player['wins'] += 1
            winner_sid = sid
            player['point'] = None
        elif total in (2,3,12):
            result = 'Krepp (Lose)'
            player['losses'] += 1
            # loser -> no winner to collect credits
            player['point'] = None
        else:
            result = f'Mail {total}'
            player['point'] = total
    else:
        # player has a point: win if hit point, lose if roll 7, otherwise continue
        if total == player['point']:
            result = 'Mail Hit (Win)'
            player['wins'] += 1
            winner_sid = sid
            player['point'] = None
        elif total == 7:
            result = '7 Rolled (Lose)'
            player['losses'] += 1
            player['point'] = None
        else:
            result = f'Rolling... (Point={player["point"]})'

    # If winner, collect 1 credit from each other player (if they have >=1)
    if winner_sid:
        total_collected = 0
        for other_sid, other in s['players'].items():
            if other_sid == winner_sid: continue
            take = 1 if other.get('credit',0) >= 1 else 0
            if take:
                other['credit'] -= 1
                total_collected += 1
        s['players'][winner_sid]['credit'] += total_collected

    # Decide next turn:
    # If player has a point (Mail) and hasn't lost/won then SAME player continues
    # If player has no point (win/lose/krepp/pop) then pass to next approved player
    if player.get('point') is None:
        # rotate to next approved player
        sids = [sid_ for sid_ in s['players'].keys() if s['players'][sid_].get('approved', True)]
        if sid in sids:
            idx = sids.index(sid)
            next_idx = (idx + 1) % len(sids)
            s['turn'] = sids[next_idx]
        else:
            # fallback: pick first
            s['turn'] = next(iter(sids)) if sids else sid
    else:
        # same player's turn (they continue)
        s['turn'] = sid

    # timestamp log
    log_text = f"{player['name']} rolled: {d1}+{d2} = {total} → {result}"
    s['log'].insert(0, (now_ts(), log_text))
    # Prepare summary payload
    payload = {
        'player': player['name'],
        'dice1': d1,
        'dice2': d2,
        'total': total,
        'result': result,
        'nextTurn': s['players'][s['turn']]['name'],
        'vs_list': " vs ".join([p['name'] for p in s['players'].values() if p.get('approved', True)]),
        'players': players_summary(s['players'])
    }
    emit('dice_rolled', payload, room=session)

@socketio.on('pass_request')
def on_pass_request(data):
    session = data.get('session'); sid = request.sid
    s = sessions.get(session)
    if not s: emit('alert','Session not found', room=sid); return
    if s['turn'] != sid:
        emit('alert','Not your turn', room=sid); return
    # pass to next approved player
    sids = [sid_ for sid_ in s['players'].keys() if s['players'][sid_].get('approved', True)]
    if sid not in sids:
        emit('alert','You cannot pass', room=sid); return
    idx = sids.index(sid)
    next_idx = (idx + 1) % len(sids)
    s['turn'] = sids[next_idx]
    payload = {
        'player': s['players'][sid]['name'],
        'dice1': 0, 'dice2': 0, 'total': 0,
        'result': 'Turn Passed',
        'nextTurn': s['players'][s['turn']]['name'],
        'vs_list': " vs ".join([p['name'] for p in s['players'].values() if p.get('approved', True)]),
        'players': players_summary(s['players'])
    }
    s['log'].insert(0, (now_ts(), f"{s['players'][sid]['name']} passed the dice"))
    emit('dice_rolled', payload, room=session)

@socketio.on('play_again')
def on_play_again(data):
    session = data.get('session'); sid = request.sid
    s = sessions.get(session)
    if not s: emit('alert','Session not found', room=sid); return
    # Only allow if the requester was the last winner (simpler: allow if they currently hold turn)
    if s.get('turn') != sid:
        emit('alert','You can only choose Play Again on your turn after winning', room=sid); return
    # Keep turn on same sid (no change)
    payload = {
        'player': s['players'][sid]['name'],
        'dice1': 0, 'dice2': 0, 'total': 0,
        'result': 'Play Again chosen — go ahead',
        'nextTurn': s['players'][sid]['name'],
        'vs_list': " vs ".join([p['name'] for p in s['players'].values() if p.get('approved', True)]),
        'players': players_summary(s['players'])
    }
    s['log'].insert(0, (now_ts(), f"{s['players'][sid]['name']} chose to play again"))
    emit('dice_rolled', payload, room=session)

# run
if __name__ == '__main__':
    socketio.run(app, debug=True, port=8000)
