import json
import os

# Constants from rucoin.py
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

class handler:
    def do_GET(self):
        chain = load_chain()
        height = len(chain) - 1 if chain else 0
        total_mined = sum(reward_for_block(i) for i in range(len(chain)))

        # Network hashrate estimate
        network_hashrate = 0
        if len(chain) >= 2:
            recent = chain[-min(10, len(chain)):]
            if len(recent) >= 2:
                time_diff = recent[-1]["timestamp"] - recent[0]["timestamp"]
                if time_diff > 0:
                    network_hashrate = (len(recent) * (2 ** 3)) / time_diff

        stats = {
            "chain_height": max(0, height),
            "block_reward": reward_for_block(height + 1),
            "halving_blocks_left": 62500 - (height % 62500) if height >= 0 else 62500,
            "network_hashrate": network_hashrate,
            "difficulty": 3,
            "total_mined": total_mined,
        }

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(stats).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()