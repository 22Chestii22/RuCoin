from http.server import BaseHTTPRequestHandler
import json
import time
import os

# In-memory pool state (в проде — Redis/DB)
pool_state = {
    "height": 0,
    "prev_hash": "0" * 64,
    "difficulty": 3,
    "workers": {},
    "last_block": 0,
    "total_paid": 0.0,
    "total_hashrate": 0.0,
}

# Константы из rucoin.py
INITIAL_REWARD = 2048
HALVING_INTERVAL = 62500
SATOSHI = 0.00000001

def reward_for_block(index: int) -> float:
    epoch = index // HALVING_INTERVAL
    reward = INITIAL_REWARD >> epoch
    min_reward = SATOSHI
    if reward < min_reward:
        reward = INITIAL_REWARD / (2 ** epoch)
        if reward < min_reward:
            return 0.0
    return float(reward)

def load_chain():
    try:
        with open("/tmp/rucoin_chain.json", "r") as f:
            return json.load(f)
    except:
        return []

def save_chain(chain):
    try:
        with open("/tmp/rucoin_chain.json", "w") as f:
            json.dump(chain, f)
    except:
        pass

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/api/pool/job":
            self.handle_job()
        elif self.path == "/api/pool/submit":
            self.handle_submit()
        elif self.path == "/api/pool/stats":
            self.handle_stats()
        else:
            self.send_error(404)

    def handle_job(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        try:
            data = json.loads(body)
            worker = data.get("worker", "anonymous")
        except:
            worker = "anonymous"

        # Регистрируем воркера
        if worker not in pool_state["workers"]:
            pool_state["workers"][worker] = {
                "shares": 0,
                "accepted": 0,
                "last_seen": time.time(),
                "hashrate": 0.0
            }
        pool_state["workers"][worker]["last_seen"] = time.time()

        # Обновляем высоту из локальной цепочки
        chain = load_chain()
        pool_state["height"] = len(chain) - 1
        if chain:
            pool_state["prev_hash"] = chain[-1]["hash"]

        response = {
            "height": pool_state["height"],
            "prev_hash": pool_state["prev_hash"],
            "difficulty": pool_state["difficulty"],
            "target_reward": reward_for_block(pool_state["height"] + 1),
            "worker": worker
        }

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

    def handle_submit(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        try:
            data = json.loads(body)
            worker = data.get("worker")
            block = data.get("block")
            address = data.get("address")

            if not all([worker, block, address]):
                self.send_json({"error": "missing fields"}, 400)
                return

            # Проверяем блок (упрощённо)
            block_hash = block.get("hash", "")
            if not block_hash.startswith("0" * pool_state["difficulty"]):
                self.send_json({"error": "insufficient difficulty", "accepted": False}, 400)
                return

            # Валидируем prev_hash
            chain = load_chain()
            expected_height = len(chain)
            if block.get("index") != expected_height:
                self.send_json({"error": "stale block height", "accepted": False}, 400)
                return

            # Добавляем в цепочку
            chain.append(block)
            save_chain(chain)

            # Обновляем состояние пула
            pool_state["height"] = expected_height
            pool_state["prev_hash"] = block["hash"]
            pool_state["last_block"] = expected_height

            # Награждаем воркера
            reward = reward_for_block(expected_height)
            pool_state["workers"][worker]["shares"] += 1
            pool_state["workers"][worker]["accepted"] += 1
            pool_state["total_paid"] += reward

            self.send_json({
                "accepted": True,
                "payout": reward,
                "height": expected_height
            })

        except Exception as e:
            self.send_json({"error": str(e), "accepted": False}, 500)

    def handle_stats(self):
        chain = load_chain()
        height = len(chain) - 1
        total_mined = sum(reward_for_block(i) for i in range(len(chain)))

        # Считаем pool hashrate
        active_workers = [w for w in pool_state["workers"].values() 
                         if time.time() - w["last_seen"] < 300]
        pool_hashrate = sum(w.get("hashrate", 0) for w in active_workers)

        # Network hashrate estimate
        network_hashrate = 0
        if len(chain) >= 2:
            recent = chain[-min(10, len(chain)):]
            if len(recent) >= 2:
                time_diff = recent[-1]["timestamp"] - recent[0]["timestamp"]
                if time_diff > 0:
                    network_hashrate = (len(recent) * (2 ** 3)) / time_diff

        stats = {
            "chain_height": height,
            "block_reward": reward_for_block(height + 1),
            "halving_blocks_left": 62500 - (height % 62500),
            "network_hashrate": network_hashrate,
            "difficulty": 3,
            "total_mined": total_mined,
            "pool_hashrate": pool_hashrate,
            "pool_miners": len(active_workers),
            "pool_last_block": pool_state["last_block"],
            "pool_paid": pool_state["total_paid"]
        }

        self.send_json(stats)

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()