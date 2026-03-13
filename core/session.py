from datetime import datetime
from typing import Dict, List, Optional


class SessionManager:
    """对局数据管理类"""

    def __init__(self, data_manager):
        self.data_manager = data_manager
        self.sessions = data_manager.load_sessions()
        self.current_id = data_manager.load_counter()

    def get_next_id(self) -> int:
        next_id = self.current_id
        self.current_id += 1
        self.data_manager.save_counter(self.current_id)
        return next_id

    def save_all(self):
        self.data_manager.save_sessions(self.sessions)

    def create_session(self, session_id: str, qq: str, nickname: str, score: int | None, group_id: str) -> Dict:
        """创建对局

        score 为 None 时，仅创建空对局，不预先加入任何玩家；
        score 为 int 时，会将创建者作为首位玩家加入。
        """
        players: list[Dict] = []
        if score is not None:
            players.append({
                "qq": qq,
                "nickname": nickname,
                "score": score,
                "timestamp": datetime.now().isoformat()
            })

        session = {
            "id": session_id,
            "created_at": datetime.now().isoformat(),
            "created_by": qq,
            "group_id": group_id,
            "players": players,
        }
        self.sessions[session_id] = session
        self.save_all()
        return session

    def get_session(self, session_id: str) -> Optional[Dict]:
        return self.sessions.get(session_id)

    def check_duplicate(self, session: Dict, qq: str) -> Optional[str]:
        for player in session['players']:
            if player['qq'] == qq:
                return player['nickname']
        return None

    def update_player_score(self, session: Dict, qq: str, new_score: int, nickname: str) -> bool:
        for player in session['players']:
            if player['qq'] == qq:
                player['score'] = new_score
                player['timestamp'] = datetime.now().isoformat()
                player['nickname'] = nickname
                return True
        return False

    def add_player(self, session: Dict, qq: str, nickname: str, score: int):
        session['players'].append({
            "qq": qq,
            "nickname": nickname,
            "score": score,
            "timestamp": datetime.now().isoformat()
        })
        self.save_all()

    def get_all_sessions(self) -> Dict:
        return self.sessions

    def remove_session(self, session_id: str):
        if session_id in self.sessions:
            del self.sessions[session_id]
            self.save_all()

    @staticmethod
    def validate_score(score_str: str) -> tuple[bool, int, str]:
        try:
            score = int(score_str)
            return True, score, ""
        except ValueError:
            return False, 0, "分数必须是数字"

    @staticmethod
    def calculate_rankings(players: List[Dict]) -> List[Dict]:
        sorted_players = sorted(players, key=lambda x: x['score'], reverse=True)
        rankings = []
        for i, player in enumerate(sorted_players, 1):
            diff = 0 if i == 1 else (sorted_players[0]['score'] - player['score']) / 1000
            rankings.append({
                "rank": i,
                "nickname": player['nickname'],
                "qq": player['qq'],
                "score": player['score'],
                "diff_from_first": round(diff, 1)
            })
        return rankings

    @staticmethod
    def format_settlement(rankings: List[Dict], session_id: int, total_score: int) -> str:
        message = f"🎴 对局 {session_id} 结算\n═══════════════\n"
        for r in rankings:
            medal = "🥇" if r["rank"] == 1 else "🥈" if r["rank"] == 2 else "🥉" if r["rank"] == 3 else "📌"
            diff_text = f" (首位差 {r['diff_from_first']}k)" if r["rank"] > 1 else " (TOP)"
            message += f"{medal} {r['rank']}位：{r['nickname']}  {r['score']}点{diff_text}\n"
        message += f"\n📊 总分：{total_score}点"
        if total_score != 100000:
            message += f"\n⚠️ 注意：总分异常（标准应为100000点），请核对分数"
        return message

    def try_settle(self, session_id: str, data_manager) -> Optional[Dict]:
        session = self.sessions.get(session_id)
        if not session or len(session['players']) != 4:
            return None
        players = session['players']
        total_score = sum(p['score'] for p in players)
        rankings = self.calculate_rankings(players)
        record = {
            "session_id": session_id,
            "settle_time": datetime.now().replace(microsecond=0).isoformat(),  # 精确到秒
            "created_at": session['created_at'],
            "players": players,
            "rankings": rankings,
            "total_score": total_score,
            "group_id": session['group_id']
        }
        data_manager.save_record(record)
        self.remove_session(session_id)
        return {"rankings": rankings, "total_score": total_score}