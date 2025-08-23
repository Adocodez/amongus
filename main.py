# File: main.py
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from datetime import datetime, timedelta
import uvicorn
import random
from threading import Timer

app = FastAPI()
win_announced = False

# ------------------------------
# Game State
# ------------------------------
players = {}  # {rfid: {"color": str, "role": str, "alive": bool, "last_kill": datetime}}
colors = ["Red", "Blue", "Green", "Yellow", "Orange", "Pink", "Purple", "Cyan", "White", "Black"]

game_state = "waiting"  # waiting / running / ended
game_start_time = None
game_winner = None  # None / "crewmates" / "impostors" / "jester" / "draw"

# New Game Parameters
game_duration = 300  # 5 minutes
task_goal = 6
required_players = 10
kill_cooldown = timedelta(seconds=75)  # 1.5 minutes

# ------------------------------
# Meeting State
# ------------------------------
meeting_active = False
meeting_start_time = None
meeting_duration = 30  # seconds
meeting_delay = 6      # seconds after death

# Tasks
total_tasks_done = 0

# ------------------------------
# Helpers
# ------------------------------
def assign_roles():
    """Assigns roles: 2 Impostors, 1 Jester, 6 Crewmates."""
    global players
    rfids = list(players.keys())
    random.shuffle(rfids)
    for rfid in rfids[:2]:
        players[rfid]["role"] = "impostor"
    players[rfids[2]]["role"] = "jester"
    for rfid in rfids[3:]:
        players[rfid]["role"] = "crewmate"
    for rfid in rfids:
        players[rfid]["alive"] = True
        players[rfid]["last_kill"] = datetime.min

def reset_game():
    """Resets the game to its initial waiting state."""
    global players, game_state, total_tasks_done, game_start_time, game_winner, meeting_active, meeting_start_time
    for rfid in players:
        players[rfid]["role"] = None
        players[rfid]["alive"] = True
        players[rfid]["last_kill"] = datetime.min
    game_state = "waiting"
    total_tasks_done = 0
    game_start_time = None
    game_winner = None
    meeting_active = False
    meeting_start_time = None

def check_win_conditions():
    global game_state, game_winner, win_announced
    if game_state != "running":
        return

    # If jester already won, skip checks
    if game_winner == "jester":
        return

    alive_crewmates = sum(1 for p in players.values() if p["alive"] and p["role"] == "crewmate")
    alive_impostors = sum(1 for p in players.values() if p["alive"] and p["role"] == "impostor")

    if total_tasks_done >= task_goal:
        game_state = "ended"
        game_winner = "crewmates"
    elif alive_crewmates <= 2:
        game_state = "ended"
        game_winner = "impostors"
    elif game_start_time:
        elapsed = (datetime.now() - game_start_time).total_seconds()
        if elapsed >= game_duration:
            game_state = "ended"
            game_winner = "draw"

    if game_state == "ended" and game_winner and not win_announced:
        win_announced = True




# ------------------------------
# API Endpoints
# ------------------------------
@app.get("/connect/{rfid}/{color}")
async def connect_player(rfid: str, color: str):
    players[rfid] = {"color": color, "role": "Crewmate", "alive": True, "last_kill": datetime.min}
    return {"status": "connected", "rfid": rfid, "color": color}

@app.post("/start")
def start_game():
    global game_state, game_start_time
    if len(players) != required_players:
        return {"error": f"Need exactly {required_players} players to start."}
    reset_game()
    assign_roles()
    game_state = "running"
    game_start_time = datetime.now()
    return {"status": "game started"}

@app.post("/reset")
def reset():
    reset_game()
    return {"status": "game reset"}

from fastapi.encoders import jsonable_encoder

@app.get("/status")
def status():
    global meeting_active, meeting_start_time
    check_win_conditions()

    remaining_time = 0
    if game_state == "running" and game_start_time:
        elapsed = (datetime.now() - game_start_time).total_seconds()
        remaining_time = max(0, game_duration - int(elapsed))

    # Meeting countdown
    meeting_remaining = 0
    if meeting_active and meeting_start_time:
        elapsed = (datetime.now() - meeting_start_time).total_seconds()
        meeting_remaining = max(0, meeting_duration - int(elapsed))
        if meeting_remaining == 0:
            meeting_active = False
            meeting_start_time = None

    for p in players.values():
        if not p["alive"]:
            p["death_type"] = p.get("death_type", "killed")

    return {
        "game_state": game_state,
        "time_remaining": remaining_time,
        "players": jsonable_encoder(players),
        "tasks_done": total_tasks_done,
        "task_goal": task_goal,
        "winner": game_winner if game_state == "ended" else None,
        "meeting_remaining": meeting_remaining
    }


@app.post("/kill/{impostor}/{target}")
def kill(impostor: str, target: str):
    global meeting_active, meeting_start_time
    if game_state != "running":
        return {"error": "Game not running"}
    if impostor not in players or target not in players:
        return {"error": "Invalid player RFID"}
    if players[impostor]["role"] != "impostor":
        return {"error": "Not an impostor"}
    if not players[impostor]["alive"]:
        return {"error": "Dead impostors cannot kill"}
    if players[target]["role"] == "impostor":
        return {"error": "Cannot kill a fellow impostor"}
    if not players[target]["alive"]:
        return {"error": "Target already dead"}

    now = datetime.now()
    if now - players[impostor]["last_kill"] < kill_cooldown:
        cooldown_left = kill_cooldown - (now - players[impostor]["last_kill"])
        return {"error": f"Kill cooldown active. {int(cooldown_left.total_seconds())}s remaining."}

    players[target]["alive"] = False
    players[target]["death_time"] = now
    players[impostor]["last_kill"] = now

    # Start meeting after delay
    def start_meeting():
        global meeting_active, meeting_start_time
        if game_state =='running':
            meeting_active = True
            meeting_start_time = datetime.now()

    Timer(meeting_delay, start_meeting).start()
    
    check_win_conditions()
    return {
        "status": f"{players[target]['color']} was killed.",
        "death_type": "killed",
        "winner": game_winner if game_state=="ended" else None
}



@app.post("/eject/{rfid}")
def eject(rfid: str):
    global game_state, game_winner, win_announced
    if game_state != "running":
        return {"error": "Game not running."}
    if rfid not in players:
        return {"error": "Player not found."}
    if not players[rfid]["alive"]:
        return {"error": "Player is already dead."}

    # Mark player dead
    players[rfid]["alive"] = False
    players[rfid]["death_type"] = "ejected"

    # If jester is ejected → jester wins immediately
    if players[rfid]["role"] == "jester":
        game_state = "ended"
        game_winner = "jester"
        win_announced = True
    else:
        check_win_conditions()  # for normal ejections

    return {
        "status": f"{players[rfid]['color']} has been ejected",
        "winner": game_winner if game_state=="ended" else None,
        "death_type": "ejected"
    }




@app.get("/role/{rfid}")
def get_role(rfid: str):
    """
    Returns a simple text with the player's color and role.
    Example: "Red: CREWMATE"
    """
    if rfid not in players:
        return "Unknown Card"
    
    player_info = players[rfid]
    role = player_info.get("role", "Unknown").upper()
    color = player_info.get("color", "Unknown")
    
    return f"{color}: {role}"

# ------------------------------
# Logistics Task Completion Endpoint
# ------------------------------
@app.post("/logistics/complete_task")
def complete_task():
    global total_tasks_done
    if game_state != "running":
        return {"error": "Game not running"}
    if total_tasks_done < task_goal:
        total_tasks_done += 1
    return {"status": f"Task completed. Total: {total_tasks_done}"}

# To store pending eject during meeting
pending_eject_rfid = None

@app.post("/special-logistics/set_eject")
def set_eject(rfid: str = Form(...)):
    global pending_eject_rfid
    if not meeting_active:
        return {"error": "Meeting not active, cannot set eject."}
    if rfid not in players or not players[rfid]["alive"]:
        return {"error": "Invalid or dead player"}
    pending_eject_rfid = rfid
    return {"status": f"{players[rfid]['color']} selected for eject after meeting"}

@app.post("/special-logistics/process_eject")
def process_eject():
    global pending_eject_rfid
    if pending_eject_rfid:
        rfid = pending_eject_rfid
        pending_eject_rfid = None
        # Actually eject player
        players[rfid]["alive"] = False
        players[rfid]["death_type"] = "ejected"
        # Check jester win
        global game_state, game_winner, win_announced
        if players[rfid]["role"] == "jester":
            game_state = "ended"
            game_winner = "jester"
            win_announced = True
        else:
            check_win_conditions()
        return {"status": f"{players[rfid]['color']} ejected after meeting"}
    return {"status": "No eject selected"}

@app.get("/special-logistics", response_class=HTMLResponse)
def special_logistics_page():
    return """
<html>
<head>
<title>Special Logistics Panel</title>
<style>
body { font-family: Arial; text-align:center; margin-top:50px; background-color:#222; color:white; }
button { font-size:1.5em; padding:10px 30px; margin:5px; cursor:pointer; }
#alert { font-size:2em; color:red; display:none; margin-top:20px; }
#tasks-status { font-size:1.5em; margin-top:20px; }
.player-btn { display:inline-block; margin:5px; padding:10px; border-radius:5px; font-size:1em; }
.selected { border: 3px solid yellow; }
</style>
</head>
<body>
<h1>Special Logistics Panel</h1>
<p>Mark ONE task as done:</p>
<button id="complete-task-btn">Complete Task</button>
<p>Current Tasks Completed: <span id="tasks-status">-</span></p>

<h2>Players Alive:</h2>
<div id="players-list"></div>

<div id="alert"></div>

<script>
let alertedDead = {};
let pendingEject = null;

function showAlert(msg){
    const alertDiv = document.getElementById('alert');
    alertDiv.innerText = msg;
    alertDiv.style.display='block';
    setTimeout(()=>{ alertDiv.style.display='none'; }, 10000);
}

// Blink background for deaths
let flashIntervals = {};
function blinkBackground(color){
    const body = document.body;
    let blink = true;
    if(flashIntervals[color]) clearInterval(flashIntervals[color]);
    flashIntervals[color] = setInterval(() => {
        body.style.backgroundColor = blink ? color : "#222";
        blink = !blink;
    }, 500);
    setTimeout(() => {
        clearInterval(flashIntervals[color]);
        body.style.backgroundColor = "#222";
        delete flashIntervals[color];
    }, 30000);
}

// Refresh status
async function refreshStatus(){
    let res = await fetch('/status');
    let data = await res.json();

    document.getElementById('tasks-status').innerText = data.tasks_done + " / " + data.task_goal;

    // Handle deaths
    for(let [rfid,p] of Object.entries(data.players)){
        if(!p.alive && !alertedDead[rfid]){
            alertedDead[rfid] = true;
            showAlert(`${p.color} DIED!`);
            blinkBackground(p.color);
        }
    }

    // Show alive players for selection
    let html = '';
    for(let [rfid,p] of Object.entries(data.players)){
        if(p.alive){
            let cls = (pendingEject===rfid) ? 'selected' : '';
            html += `<button class="player-btn ${cls}" onclick="selectEject('${rfid}')">${p.color}</button>`;
        }
    }
    document.getElementById('players-list').innerHTML = html;

    // Auto eject after meeting ends
    if(data.meeting_remaining===0 && pendingEject){
        await fetch('/special-logistics/process_eject', {method:'POST'});
        pendingEject = null;
    }
}

// Select who to eject
async function selectEject(rfid){
    pendingEject = rfid;
    await fetch('/special-logistics/set_eject', {
        method:'POST',
        body: new URLSearchParams({'rfid': rfid})
    });
    refreshStatus();
}

// Complete task button
document.getElementById('complete-task-btn').addEventListener('click', async ()=>{
    await fetch('/logistics/complete_task', {method:'POST'});
    await refreshStatus();
});

setInterval(refreshStatus, 1000);
window.onload = refreshStatus;
</script>
</body>
</html>
"""




# ------------------------------
# Logistics Page
# ------------------------------
@app.get("/logistics", response_class=HTMLResponse)
def logistics_page():
    return """
<html>
<head>
<title>Logistics Panel</title>
<style>
body { font-family: Arial; text-align:center; margin-top:50px; background-color:#222; color:white; }
button { font-size:2em; padding:20px 40px; margin:5px; cursor:pointer; }
#alert { font-size:2em; color:red; display:none; margin-top:20px; }
#tasks-status { font-size:1.5em; margin-top:20px; }
</style>
</head>
<body>
<h1>Logistics Panel</h1>
<button id="complete-task-btn">Mark ONE Task as Done</button>
<p>Current Tasks Completed: <span id="tasks-status">-</span></p>
<div id="alert"></div>

<script>
let alertedDead = {};
let flashIntervals = {};

function showAlert(msg){
    const alertDiv = document.getElementById('alert');
    alertDiv.innerText = msg;
    alertDiv.style.display='block';
    setTimeout(()=>{ alertDiv.style.display='none'; }, 10000);
}

// Blink background in color of dead player
function blinkBackground(color){
    const body = document.body;
    let blink = true;

    if(flashIntervals[color]) clearInterval(flashIntervals[color]); // clear if already blinking

    flashIntervals[color] = setInterval(() => {
        body.style.backgroundColor = blink ? color : "#222";
        blink = !blink;
    }, 500); // toggle every 0.5s

    // Stop blinking after 30s and reset
    setTimeout(() => {
        clearInterval(flashIntervals[color]);
        body.style.backgroundColor = "#222";
        delete flashIntervals[color];
    }, 30000);
}

async function refreshStatus(){
    let res = await fetch('/status');
    let data = await res.json();

    document.getElementById('tasks-status').innerText = data.tasks_done + " / " + data.task_goal;

    for(let [rfid,p] of Object.entries(data.players)){
        if(!p.alive && !alertedDead[rfid]){
            showAlert(`${p.color} (${rfid}) DIED!`);
            alertedDead[rfid] = true;
            blinkBackground(p.color); // <-- blink immediately
        }
    }
}

document.getElementById('complete-task-btn')?.addEventListener('click', async ()=>{
    await fetch('/logistics/complete_task', {method:'POST'});
    await refreshStatus();
});

setInterval(refreshStatus, 1000);
window.onload = refreshStatus;
</script>


</body>
</html>
"""


# ------------------------------
# Main Hall Page (with JS TTS)
# ------------------------------
@app.get("/", response_class=HTMLResponse)
def main_hall_page():
    return """
<html>
<head>
<title>Main Hall</title>
<style>
body { font-family: Arial; background-color:#1a1a1a; color:white; text-align:center; }
h1 { font-size:3em; }
.container { display:flex; justify-content:space-around; margin-top:50px; }
.panel { background-color:#333; padding:20px; border-radius:10px; width:30%; }
#alert { font-size:2em; color:red; display:none; margin-top:20px; }
#meeting { font-size:2em; color:yellow; display:none; margin-top:10px; }
#winner-display { font-size:2.5em; color:lime; margin-top:20px; }
</style>
</head>
<body>
<h1>Game Status</h1>
<h2 id="winner-display"></h2>
<div class="container">
<div class="panel">
<h2>Time Remaining</h2>
<p id="time" style="font-size:2.5em;">-</p>
</div>
<div class="panel">
<h2>Tasks Completed</h2>
<p id="tasks" style="font-size:2.5em;">- / -</p>
</div>
<div class="panel">
<h2>Players Alive</h2>
<p id="alive-players" style="font-size:2.5em;">- / -</p>
</div>
</div>
<div id="alert"></div>
<div id="meeting">Meeting in Progress: <span id="meeting-count">-</span></div>

<script>
let previousAliveState = {};
let announcedDead = {};
let winnerAnnounced = false;
let meetingActive = false;
let meetingInterval = null;
let meetingTTSInterval = null;

function speak(msg){
    if('speechSynthesis' in window){
        const utter = new SpeechSynthesisUtterance(msg);
        utter.rate = 1;
        window.speechSynthesis.speak(utter);
    }
}

function showAlert(msg){
    const alertDiv = document.getElementById('alert');
    alertDiv.innerText = msg;
    alertDiv.style.display='block';
    setTimeout(()=>{ alertDiv.style.display='none'; }, 10000);
}

function resetForNewGame(){
    winnerAnnounced = false;
    meetingActive = false;
    announcedDead = {};
    if(meetingInterval) clearInterval(meetingInterval);
    if(meetingTTSInterval) clearInterval(meetingTTSInterval);
    document.getElementById('winner-display').innerText = "";
    document.getElementById('meeting').style.display = 'none';
    previousAliveState = {};
}

// Refresh status every second
async function refreshStatus(){
    let res = await fetch('/status');
    let data = await res.json();

    // Reset for new game
    if(data.game_state=="running" && winnerAnnounced && !data.winner){
        resetForNewGame();
    }

    // Update main stats
    document.getElementById('time').innerText = data.time_remaining + "s";
    document.getElementById('tasks').innerText = data.tasks_done + " / " + data.task_goal;
    let aliveCount = Object.values(data.players).filter(p=>p.alive).length;
    document.getElementById('alive-players').innerText = aliveCount + " / " + Object.keys(data.players).length;

    // Handle kills & ejections with 5s delay
    for(let [rfid,p] of Object.entries(data.players)){
        if(previousAliveState[rfid] === undefined) previousAliveState[rfid] = p.alive;

        if(previousAliveState[rfid] && !p.alive && !announcedDead[rfid]){
            announcedDead[rfid] = true;
            let action = p.death_type;
            setTimeout(()=>{  // 5s delay
                speak(`${p.color} has been ${action}.`);
                showAlert(`${p.color} (${action.toUpperCase()})!`);
            }, 5000);
        }
        previousAliveState[rfid] = p.alive;
    }

    // Winner announcement
    if(data.game_state === "ended" && data.winner && !winnerAnnounced){
        winnerAnnounced = true;
        let winnerText = data.winner.toUpperCase();
        document.getElementById('winner-display').innerText = winnerText + " WINS!";
        speak(winnerText + " wins!");
    }

    // Meeting countdown 10 → 1 in 30s
    if(data.meeting_remaining > 0){
        document.getElementById('meeting').style.display = 'block';
        document.getElementById('meeting-count').innerText = data.meeting_remaining + "s left";

        if(!meetingActive){
            meetingActive = true;
            speak('Meeting has started.');

            let count = 10;
            if(meetingTTSInterval) clearInterval(meetingTTSInterval);
            meetingTTSInterval = setInterval(()=>{
                if(count > 0){
                    speak(count.toString());
                    count--;
                } else {
                    speak("Meeting over");
                    clearInterval(meetingTTSInterval);
                }
            }, 2750); // 3s per number

            if(meetingInterval) clearInterval(meetingInterval);
            meetingInterval = setInterval(()=>{
                let remaining = parseInt(document.getElementById('meeting-count').innerText);
                if(remaining > 1){
                    document.getElementById('meeting-count').innerText = (remaining-1) + "s left";
                } else {
                    document.getElementById('meeting').style.display = 'none';
                    meetingActive = false;
                    clearInterval(meetingInterval);
                }
            }, 1000);
        }
    }
}



setInterval(refreshStatus, 1000);
window.onload = refreshStatus;
</script>
</body>
</html>

"""



# ------------------------------
# Admin Page (Silent)
# ------------------------------
@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    return """
<html>
<head>
<title>Admin Panel</title>
<style>
body { font-family: Arial; text-align:center; margin-top:50px; background-color:#111; color:white; }
button { font-size:1.2em; padding:10px 30px; margin:5px; cursor:pointer; }
#announcements { font-size:1.5em; color:yellow; margin-top:20px; }
#status { font-size:1.5em; margin-top:20px; }
</style>
</head>
<body>
<h1>Admin Panel</h1>
<button onclick="startGame()">Start Game</button>
<button onclick="resetGame()">Reset Game</button>

<div id="status">
<p>Game State: <span id="game-state">-</span></p>
<p>Tasks: <span id="tasks">-</span></p>
<p>Time Remaining: <span id="time">-</span>s</p>
</div>

<div id="players-list"></div>
<div id="announcements"></div>

<script>
let previousAliveState = {};
let meetingCountdownRunning = false;

function showAnnouncement(msg){
    const ann = document.getElementById('announcements');
    ann.innerText = msg;
    setTimeout(()=>{ ann.innerText=''; }, 10000);
}

async function startGame(){ await fetch('/start',{method:'POST'}); refreshStatus(); }
async function resetGame(){ await fetch('/reset',{method:'POST'}); refreshStatus(); }
async function ejectPlayer(rfid){ await fetch('/eject/'+rfid,{method:'POST'}); refreshStatus(); }

async function refreshStatus(){
    let res = await fetch('/status'); 
    let data = await res.json();

    document.getElementById('game-state').innerText = data.game_state.toUpperCase();
    document.getElementById('tasks').innerText = data.tasks_done + " / " + data.task_goal;
    document.getElementById('time').innerText = data.time_remaining;

    let html='';
    for(let [rfid,p] of Object.entries(data.players)){
        html+=`<p>${rfid} (${p.color}) - ${p.role} - ${p.alive?'ALIVE':'DEAD'} <button onclick="ejectPlayer('${rfid}')">Eject</button></p>`;
    }
    document.getElementById('players-list').innerHTML = html;

    for(let [rfid,p] of Object.entries(data.players)){
        if(previousAliveState[rfid]===undefined) previousAliveState[rfid] = p.alive;
        if(previousAliveState[rfid] && !p.alive){
            showAnnouncement(`${p.color} (${rfid}) DIED!`);
        }
        previousAliveState[rfid] = p.alive;
    }

    if(data.meeting_remaining>0 && !meetingCountdownRunning){
        meetingCountdownRunning = true;
        let count=1;
        showAnnouncement('Meeting Started!');
        const interval = setInterval(()=>{
            showAnnouncement('Meeting in progress: '+count+'/10');
            count++;
            if(count>10){ clearInterval(interval); meetingCountdownRunning=false; }
        }, 3000);
    }

    if(data.winner){
        if(data.winner=="draw") showAnnouncement("DRAW!");
        else showAnnouncement(data.winner.toUpperCase()+" WINS!");
    }
}

setInterval(refreshStatus,1000);
window.onload = refreshStatus;
</script>
</body>
</html>
"""

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
