from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


def _parse_time(t: str) -> datetime:
    try:
        return datetime.fromisoformat(t)
    except Exception:
        return datetime.min


class StatsManager:
    """负责从结算数据中生成统计信息（玩家战绩 / 役满统计 / 排行榜）。"""

    def __init__(self, data_manager):
        self.data_manager = data_manager

    def _load_records(self) -> List[Dict[str, Any]]:
        return self.data_manager.load_records()

    def _resolve_player_ids(self, identifier: Optional[str], records: List[Dict[str, Any]]) -> Tuple[str, str]:
        """返回 (qq, nickname) 作为唯一标识，如果 identifier 为空则返回 ("", "")."""
        if identifier is None:
            return "", ""

        identifier = str(identifier)
        if not identifier:
            return "", ""

        # 如果是数字且长度较长，优先认为是 qq
        if identifier.isdigit() and len(identifier) >= 5:
            return identifier, ""

        # 尝试按昵称匹配
        for record in records:
            for p in record.get("players", []):
                if p.get("nickname") == identifier:
                    return p.get("qq", ""), identifier

        # fallback: treat as qq
        return identifier, ""

    def get_player_records(self, identifier: Optional[str]) -> List[Dict[str, Any]]:
        records = self._load_records()
        qq, nickname = self._resolve_player_ids(identifier, records)
        if not qq and not nickname:
            return []

        player_records = []
        for record in records:
            for p in record.get("players", []):
                if qq and p.get("qq") == qq:
                    player_records.append(record)
                    break
                if nickname and p.get("nickname") == nickname:
                    player_records.append(record)
                    break
        return sorted(player_records, key=lambda r: _parse_time(r.get("settle_time", "")), reverse=True)

    def calc_player_stats(self, identifier: Optional[str]) -> Dict[str, Any]:
        records = self.get_player_records(identifier)
        total = len(records)
        if total == 0:
            return {}

        rank_counts = Counter()
        score_diffs = []
        rankings = []
        best = None
        worst = None

        for record in records:
            settle_time = record.get("settle_time")
            session_id = record.get("session_id")
            for r in record.get("rankings", []):
                if (r.get("qq") == self._resolve_player_ids(identifier, records)[0]) or (
                    r.get("nickname") == identifier
                ):
                    rank = int(r.get("rank", 0))
                    rank_counts[rank] += 1
                    rankings.append((settle_time, rank))
                    # score diff
                    score = int(r.get("score", 0))
                    score_diffs.append(score - 25000)
                    if best is None or score > best[1]:
                        best = (session_id, score)
                    if worst is None or score < worst[1]:
                        worst = (session_id, score)
                    break

        avg_rank = sum(r for _, r in rankings) / total if total else 0
        avg_diff = sum(score_diffs) / total if total else 0

        # 实力分计算（权重: 1位*100 + 2位*50 + 3位*0 + 4位*-150）
        score_value = (
            rank_counts.get(1, 0) * 100
            + rank_counts.get(2, 0) * 50
            + rank_counts.get(3, 0) * 0
            + rank_counts.get(4, 0) * -150
        )
        rating_score = score_value / total

        # 评分等级
        if rating_score >= 3.0:
            rank_grade = "S"
        elif rating_score >= 2.0:
            rank_grade = "A"
        elif rating_score >= 1.0:
            rank_grade = "B"
        elif rating_score >= 0.0:
            rank_grade = "C"
        else:
            rank_grade = "D"

        # 最近 10 局（按结算时间排序）
        recent = [r for _, r in sorted(rankings, key=lambda x: _parse_time(x[0]))][-10:]
        recent_trend = recent

        return {
            "total_games": total,
            "avg_rank": round(avg_rank, 2),
            "rank_counts": {i: rank_counts.get(i, 0) for i in range(1, 5)},
            "rank_rates": {i: round(rank_counts.get(i, 0) / total * 100, 1) for i in range(1, 5)},
            "avg_diff": round(avg_diff, 1),
            "rating_score": round(rating_score, 2),
            "rating_grade": rank_grade,
            "recent_trend": recent_trend,
            "best": best,
            "worst": worst,
        }

    def get_yakuman_stats(self, identifier: Optional[str]) -> Dict[str, Any]:
        records = self.get_player_records(identifier)
        total_games = len(records)
        yakumans = []
        for record in records:
            for p in record.get("players", []):
                if (p.get("qq") == self._resolve_player_ids(identifier, records)[0]) or (
                    p.get("nickname") == identifier
                ):
                    for y in p.get("yakuman", []):
                        yakumans.append({**y, "session_id": record.get("session_id")})
                    break

        total_yakuman = len(yakumans)
        density = round(total_yakuman / total_games * 100, 2) if total_games else 0
        dist = Counter(y.get("type") for y in yakumans)

        with_image = [y for y in yakumans if y.get("image_url")]
        recent = sorted(yakumans, key=lambda y: _parse_time(y.get("created_at", "")), reverse=True)[:3]

        return {
            "total_yakuman": total_yakuman,
            "density": density,
            "distribution": dict(dist.most_common()),
            "with_image": with_image,
            "recent": recent,
        }

    def get_leaderboard(self, board_type: str = "power") -> List[Dict[str, Any]]:
        records = self._load_records()
        players: Dict[str, Dict[str, Any]] = {}

        for record in records:
            for r in record.get("rankings", []):
                qq = r.get("qq")
                if not qq:
                    continue
                if qq not in players:
                    players[qq] = {
                        "qq": qq,
                        "nickname": r.get("nickname", ""),
                        "games": 0,
                        "firsts": 0,
                        "yakuman": 0,
                        "score_sum": 0,
                        "power_score": 0,
                    }
                p = players[qq]
                p["games"] += 1
                rank = int(r.get("rank", 0))
                if rank == 1:
                    p["firsts"] += 1
                p["score_sum"] += int(r.get("score", 0))
                p["power_score"] += (4 if rank == 1 else 2 if rank == 2 else 0 if rank == 3 else -4)

        # yakuman
        for record in records:
            for p in record.get("players", []):
                qq = p.get("qq")
                if qq and qq in players and p.get("yakuman"):
                    players[qq]["yakuman"] += len(p.get("yakuman", []))

        # 计算指标
        for p in players.values():
            games = p["games"]
            p["top_rate"] = round(p["firsts"] / games * 100, 1) if games else 0
            p["power_score_avg"] = round(p["power_score"] / games, 2) if games else 0
        
        # 排行
        if board_type == "power":
            key = "power_score_avg"
            reverse = True
        elif board_type == "yakuman":
            key = "yakuman"
            reverse = True
        elif board_type == "top":
            key = "top_rate"
            reverse = True
        elif board_type == "iron":
            key = "games"
            reverse = True
        else:
            key = "power_score_avg"
            reverse = True

        result = sorted(players.values(), key=lambda x: x.get(key, 0), reverse=reverse)
        return result[:10]

    def get_love_hate(self, identifier: Optional[str], mode: str) -> Optional[str]:
        """mode: 'love' (你1时对方4最多) or 'hate' (你4时对方1最多)"""
        records = self.get_player_records(identifier)
        if not records:
            return None

        qq, _ = self._resolve_player_ids(identifier, records)
        counter = Counter()

        for record in records:
            ranks = {r["rank"]: r for r in record.get("rankings", [])}
            if mode == "love":
                # 你1时，找4
                if ranks.get(1, {}).get("qq") == qq:
                    target = ranks.get(4, {}).get("nickname")
                    if target:
                        counter[target] += 1
            else:
                # hate：你4时，找1
                if ranks.get(4, {}).get("qq") == qq:
                    target = ranks.get(1, {}).get("nickname")
                    if target:
                        counter[target] += 1

        if not counter:
            return None
        return counter.most_common(1)[0][0]
