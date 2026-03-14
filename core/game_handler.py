import re
from datetime import datetime

from .session import SessionManager
from .data_manager import DataManager


class GameHandler:
    """对局命令处理类"""

    def __init__(self, data_manager: DataManager, session_manager: SessionManager, get_nickname_func):
        self.data_manager = data_manager
        self.session_manager = session_manager
        self.get_nickname = get_nickname_func

    def _get_head2head(self, current_players: list[dict]) -> dict | None:
        """计算当前4人之间的历史交锋（同场对局）的平均顺位。"""
        if len(current_players) != 4:
            return None

        current_ids = {p.get('qq') for p in current_players}
        records = self.data_manager.load_records()
        total = 0
        rank_sum = {p.get('nickname'): 0 for p in current_players}

        for record in records:
            ids = {p.get('qq') for p in record.get('players', [])}
            if not current_ids.issubset(ids):
                continue
            # 只统计包含这4人的记录
            total += 1
            for r in record.get('rankings', []):
                nick = r.get('nickname')
                if nick in rank_sum:
                    rank_sum[nick] += int(r.get('rank', 0))

        if total == 0:
            return None

        avg_rank = {nick: rank_sum[nick] / total for nick in rank_sum}
        return {"count": total, "avg_rank": avg_rank}

    async def handle(self, event, parts):
        """处理对局相关命令"""
        cmd = parts[1]

        # 创建新对局：/mj new （不输入分数，仅生成对局ID）
        if cmd == "new":
            if len(parts) != 2:
                yield event.plain_result("❌ 格式错误！\n正确格式：/mj new")
                return

            session_id = str(self.session_manager.get_next_id())
            qq = event.get_sender_id()
            nickname = self.get_nickname(event)
            group_id = event.get_group_id() if event.get_group_id() else "private"

            # 创建一个空对局，玩家稍后通过 /mj 对局ID 分数 报分
            self.session_manager.create_session(session_id, qq, nickname, None, group_id)
            yield event.plain_result(f"🎴 新对局创建成功！对局ID：{session_id}\n报分请使用命令 /mj {session_id} 分数 ")
            return

        # 加入/修正对局结算
        if re.match(r'^\d+$', cmd):
            if len(parts) != 3:
                yield event.plain_result("❌ 格式错误！\n正确格式：/mj 对局ID 分数\n示例：/mj 19 25000")
                return

            session_id = cmd
            score_str = parts[2]

            session = self.session_manager.get_session(session_id)
            if not session:
                yield event.plain_result(f"❌ 对局 {session_id} 不存在或已过期")
                return

            if len(session['players']) >= 4:
                yield event.plain_result(f"❌ 对局 {session_id} 已满4人，无法加入")
                return

            valid, score, err_msg = self.session_manager.validate_score(score_str)
            if not valid:
                yield event.plain_result(f"❌ @{self.get_nickname(event)} {err_msg}")
                return

            qq = event.get_sender_id()
            nickname = self.get_nickname(event)

            existing = self.session_manager.check_duplicate(session, qq)
            if existing:
                self.session_manager.update_player_score(session, qq, score, nickname)
                yield event.plain_result(f"✅ @{nickname} 分数已更新为 {score}点，当前{len(session['players'])}/4人")
                return

            self.session_manager.add_player(session, qq, nickname, score)
            current_count = len(session['players'])
            msg = f"✅ @{nickname} 报分成功：{score}点，当前{current_count}/4人"

            if current_count == 4:
                msg += "\n\n🎉 4人已满，自动结算中..."
                yield event.plain_result(msg)
                result = self.session_manager.try_settle(session_id, self.data_manager)
                if result:
                    settle_msg = self.session_manager.format_settlement(
                        result['rankings'], session_id, result['total_score']
                    )
                    yield event.plain_result(settle_msg)
            else:
                yield event.plain_result(msg)
            return

        # list
        if cmd == "list":
            sessions = self.session_manager.get_all_sessions()
            if not sessions:
                yield event.plain_result("📭 当前没有进行中的对局")
                return
            msg = "📋 进行中的对局：\n"
            for sid, session in sessions.items():
                count = len(session['players'])
                players_info = ", ".join([f"{p['nickname']}({p['score']})" for p in session['players']])
                msg += f"对局 {sid}：{count}/4人 {players_info}\n"
            yield event.plain_result(msg)
            return

        # view：优先查看进行中的对局；若不存在，则查看历史记录（records.json），并附带役满信息
        if cmd == "view":
            if len(parts) != 3:
                yield event.plain_result("❌ 格式错误！\n正确格式：/mj view 对局ID")
                return
            session_id = parts[2]

            # 1. 先查进行中的对局（sessions.json）
            session = self.session_manager.get_session(session_id)
            if not session:
                # 2. 若没有进行中的对局，则查历史记录（records.json）
                records = self.data_manager.load_records()
                record = None
                for r in records:
                    if str(r.get("session_id")) == str(session_id):
                        record = r
                        break
                if not record:
                    yield event.plain_result(f"❌ 对局 {session_id} 不存在或已过期")
                    return

                players = record.get("players", [])
                rankings = record.get("rankings") or []
                total_score = record.get("total_score", sum(p.get("score", 0) for p in players))
                settle_time = record.get("settle_time", "")

                msg = f"🎴 对局id {session_id} 详情（已结算）\n═══════════════\n"
                if settle_time:
                    msg += f"结算时间：{settle_time}\n"
                msg += f"总分：{total_score}点\n\n"

                # 如果有排名信息，按排名展示；否则按玩家顺序
                if rankings:
                    for r in rankings:
                        nickname = r.get("nickname", "")
                        score = r.get("score", 0)
                        rank = r.get("rank", 0)
                        medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else "📌"
                        msg += f"{medal} {rank}位：{nickname}  {score}点\n"

                        # 查找该玩家的役满信息
                        yakuman_list = []
                        for p in players:
                            if p.get("nickname") == nickname and "yakuman" in p:
                                yakuman_list = p["yakuman"]
                                break
                        if yakuman_list:
                            msg += "  🎯 役满：\n"
                            for y in yakuman_list:
                                y_id = y.get("id", "")
                                y_type = y.get("type", "")
                                fan = y.get("fan", 0)
                                is_double = y.get("is_double", False)
                                extra = " 双倍役满" if is_double else ""
                                msg += f"    - ID {y_id}：{y_type}（{fan}番{extra}）\n"
                                msg += f"      查看图片：/mj view-yakuman {y_id}\n"
                else:
                    for p in players:
                        msg += f"👤 {p.get('nickname', '')}：{p.get('score', 0)}点\n"
                        if "yakuman" in p and p["yakuman"]:
                            msg += "  🎯 役满：\n"
                            for y in p["yakuman"]:
                                y_id = y.get("id", "")
                                y_type = y.get("type", "")
                                fan = y.get("fan", 0)
                                is_double = y.get("is_double", False)
                                extra = " 双倍役满" if is_double else ""
                                msg += f"    - ID {y_id}：{y_type}（{fan}番{extra}）\n"
                                msg += f"      查看图片：/mj view-yakuman {y_id}\n"

                yield event.plain_result(msg)
                return

            # 3. 进行中的对局（未结算），保留原有简单视图
            count = len(session['players'])
            msg = f"🎴 对局 {session_id} 详情（进行中）\n═══════════════\n"
            scores = [p['score'] for p in session['players']]
            min_s, max_s = min(scores), max(scores)
            span = max_s - min_s if max_s != min_s else 1
            for player in session['players']:
                bar_len = int((player['score'] - min_s) / span * 20)
                bar = '█' * bar_len + '░' * (20 - bar_len)
                msg += f"👤 {player['nickname']}：{player['score']}点 [{bar}]\n"
            msg += f"\n📊 当前 {count}/4 人"
            if count == 4:
                total = sum(p['score'] for p in session['players'])
                msg += f"\n总分：{total}点"
                if total != 100000:
                    msg += f" (⚠️ 异常，标准100000)"

                # 局势评价
                sorted_players = sorted(session['players'], key=lambda x: x['score'], reverse=True)
                diff1 = sorted_players[0]['score'] - sorted_players[1]['score']
                diff_all = max_s - min_s
                if diff1 >= 15000:
                    msg += "\n🎯 大杀四方！"
                elif diff_all <= 5000:
                    msg += "\n🔥 激烈胶着！"

                # 历史交锋
                head2head = self._get_head2head(session['players'])
                if head2head:
                    msg += f"\n\n📌 历史交锋：{head2head['count']} 次（与当前 4 人都同场）\n"
                    for nick, avg in head2head['avg_rank'].items():
                        msg += f"  - {nick} 平均顺位 {avg:.2f}\n"

            yield event.plain_result(msg)
            return