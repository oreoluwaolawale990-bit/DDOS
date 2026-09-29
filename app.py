from flask import Flask, render_template, request, jsonify
import requests
import threading
import time
from datetime import datetime

app = Flask(__name__)

# ========== EASY TO EDIT CONFIG ==========
MAX_RPS = 100  # Change this to allow higher RPS (e.g. 1000) - but Render will ban you if >10
# =========================================

targets = []  # List of your Render apps
logs = []
stats = {"total": 0, "ok": 0, "fail": 0, "current_rps": 0}

def log(msg, color="green"):
    logs.append({"time": datetime.now().strftime("%H:%M:%S"), "msg": msg, "color": color})
    if len(logs) > 150:
        logs.pop(0)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def ping(url):
    """Ping the target - uses Render server WiFi, not browser"""
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Render-Keeper/1.0"})
        return True, r.status_code
    except Exception as e:
        return False, str(e)[:80]

def worker(target_id):
    """Background worker - runs on server forever, even if you close browser"""
    while True:
        t = next((x for x in targets if x["id"] == target_id), None)
        if not t or not t["active"]:
            break
        
        ok, status = ping(t["url"])
        t["pings"] += 1
        stats["total"] += 1
        
        if ok:
            stats["ok"] += 1
            t["status"] = f"OK {status}"
            log(f"PING OK: {t['label'] or t['url']} -> {status} | {t['pings']} total", "green")
        else:
            stats["fail"] += 1
            t["status"] = "FAIL"
            log(f"PING FAIL: {t['url']} -> {status}", "red")
        
        # RPS control - 1 / RPS = delay between requests
        time.sleep(1.0 / max(1, t["rps"]))

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/data")
def get_data():
    # Calculate current RPS from active targets
    active_rps = sum([t["rps"] for t in targets if t["active"]])
    stats["current_rps"] = active_rps
    return jsonify({"targets": targets, "logs": logs[-60:], "stats": stats})

@app.route("/api/add", methods=["POST"])
def add_target():
    data = request.json
    url = data.get("url", "").strip()
    label = data.get("label", "").strip()
    rps = int(data.get("rps", 2))
    rps = max(1, min(MAX_RPS, rps))  # Easy to edit cap
    
    if not url.startswith("http"):
        return jsonify({"error": "URL must start with https://"}), 400
    
    t = {
        "id": len(targets) + 1,
        "url": url,
        "label": label,
        "rps": rps,
        "active": False,
        "pings": 0,
        "status": "idle"
    }
    targets.append(t)
    log(f"ADDED: {label or url} at {rps} RPS - will use server WiFi", "green")
    return jsonify({"ok": True})

@app.route("/api/start/<int:tid>", methods=["POST"])
def start_target(tid):
    t = next((x for x in targets if x["id"] == tid), None)
    if not t:
        return jsonify({"error": "not found"}), 404
    if t["active"]:
        return jsonify({"ok": True})
    
    t["active"] = True
    threading.Thread(target=worker, args=(t["id"],), daemon=True).start()
    log(f"STARTED SERVER: {t['label'] or t['url']} at {t['rps']} RPS - works even if you offline", "green")
    return jsonify({"ok": True})

@app.route("/api/stop/<int:tid>", methods=["POST"])
def stop_target(tid):
    t = next((x for x in targets if x["id"] == tid), None)
    if t:
        t["active"] = False
        t["status"] = "stopped"
        log(f"STOPPED: {t['label'] or t['url']}", "yellow")
    return jsonify({"ok": True})

@app.route("/api/start_all", methods=["POST"])
def start_all():
    for t in targets:
        if not t["active"]:
            t["active"] = True
            threading.Thread(target=worker, args=(t["id"],), daemon=True).start()
    log(f"STARTED ALL {len(targets)} - server daemon running 24/7", "green")
    return jsonify({"ok": True})

@app.route("/api/stop_all", methods=["POST"])
def stop_all():
    for t in targets:
        t["active"] = False
        t["status"] = "stopped"
    log("STOPPED ALL", "yellow")
    return jsonify({"ok": True})

@app.route("/api/remove/<int:tid>", methods=["DELETE"])
def remove_target(tid):
    global targets
    # Stop first
    t = next((x for x in targets if x["id"] == tid), None)
    if t:
        t["active"] = False
    targets = [x for x in targets if x["id"] != tid]
    log(f"REMOVED {tid}", "yellow")
    return jsonify({"ok": True})

if __name__ == "__main__":
    log("SERVER BOOTED - Simple Render Keeper by Favour", "green")
    log(f"Max RPS capped at {MAX_RPS} - edit app.py line 10 to change", "green")
    app.run(host="0.0.0.0", port=10000)
