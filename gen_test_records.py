import json
import random
from pathlib import Path
from datetime import datetime, timedelta

base_path = Path(__file__).parent
data_dir = base_path / "data"
data_dir.mkdir(exist_ok=True)
records_file = data_dir / "records.json"

# 固定包含的测试玩家
TEST_PLAYER = ("364535376", "寿司おいしいよ")

player_pool = [
    TEST_PLAYER,
    ("10001", "东风"),
    ("10002", "南风"),
    ("10003", "西风"),
    ("10004", "北风"),
    ("10005", "小明"),
    ("10006", "小红"),
    ("10007", "小张"),
    ("10008", "小李"),
]

def gen_one_record(idx: int) -> dict:
    now = datetime.now()
    created_at = now - timedelta(days=idx + 1)
    settle_time = created_at + timedelta(minutes=30)

    # 固定包含 TEST_PLAYER，再随机选 3 个其他玩家
    others = [p for p in player_pool if p != TEST_PLAYER]
    players_base = [TEST_PLAYER] + random.sample(others, 3)

    # 以 25000 为基准，总分固定 100000
    scores = [25000, 25000, 25000, 25000]
    # 生成一些小波动，但总和为 0
    deltas = [random.randint(-6000, 6000) for _ in range(4)]
    s = sum(deltas)
    # 调整最后一个，保证总和为 0
    deltas[-1] -= s
    scores = [25000 + d for d in deltas]

    players = []
    for (qq, nickname), score in zip(players_base, scores):
        players.append({
            "qq": qq,
            "nickname": nickname,
            "score": score,
            "timestamp": settle_time.replace(microsecond=0).isoformat(),
        })

    # 根据分数生成排名
    sorted_players = sorted(players, key=lambda x: x["score"], reverse=True)
    rankings = []
    for rank, p in enumerate(sorted_players, start=1):
        diff = 0 if rank == 1 else (sorted_players[0]["score"] - p["score"]) / 1000
        rankings.append({
            "rank": rank,
            "nickname": p["nickname"],
            "qq": p["qq"],
            "score": p["score"],
            "diff_from_first": round(diff, 1),
        })

    total_score = sum(p["score"] for p in players)

    record = {
        "session_id": str(1000 + idx),
        "settle_time": settle_time.replace(microsecond=0).isoformat(),
        "created_at": created_at.replace(microsecond=0).isoformat(),
        "players": players,
        "rankings": rankings,
        "total_score": total_score,
        "group_id": "test_group",
    }
    return record

records = [gen_one_record(i) for i in range(50)]

with open(records_file, "w", encoding="utf-8") as f:
    json.dump(records, f, ensure_ascii=False, indent=2)

print(f"已生成 {len(records)} 条测试记录到 {records_file}")