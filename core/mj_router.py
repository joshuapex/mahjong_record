import re

from astrbot.api.event import AstrMessageEvent


class MJCommandRouter:
    """负责解析 /mj 相关命令，并交给具体模块处理。"""

    def __init__(
        self,
        data_manager,
        session_manager,
        chart_generator,
        yakuman_mgr,
        stats_mgr,
        game_handler,
        html_render,
        get_nickname,
        admin_ids=None,
    ):
        self.data_manager = data_manager
        self.session_manager = session_manager
        self.chart_generator = chart_generator
        self.yakuman_mgr = yakuman_mgr
        self.stats_mgr = stats_mgr
        self.game_handler = game_handler
        self.html_render = html_render
        self.get_nickname = get_nickname
        self.admin_ids = set(admin_ids or [])

    def _is_admin(self, event: AstrMessageEvent) -> bool:
        """判断用户是否为管理员（可删除对局等权限）。

        优先尝试使用 AstrBot 事件中可能存在的管理员/群主标识字段，
        若没有则回退到环境变量配置（admin_ids）。
        """
        # 尝试从事件本身读取权限标识
        for flag in ("is_admin", "is_owner", "is_group_admin", "is_group_owner", "is_superuser"):
            if getattr(event, flag, False):
                return True

        # 如果事件中有 sender 对象（可能含权限字段）
        sender_obj = getattr(event, "sender", None)
        if sender_obj:
            for flag in ("is_admin", "is_owner", "role", "authority"):
                if hasattr(sender_obj, flag):
                    val = getattr(sender_obj, flag)
                    if isinstance(val, bool) and val:
                        return True
                    if isinstance(val, str) and val.lower() in ("admin", "owner", "master"):
                        return True

        # 退回到手动配置的管理员列表
        try:
            sender_id = event.get_sender_id()
        except Exception:
            sender_id = None
        return sender_id in self.admin_ids

    async def handle_mj_command(self, event: AstrMessageEvent):
        message_str = event.message_str.strip()
        parts = message_str.split()

        if len(parts) < 2:
            yield event.plain_result(
                "❌ 格式错误！\n使用 /mj new 创建新对局\n或 /mj 对局ID 分数 加入/修正对局结算\n或 /mj help 查看帮助"
            )
            return

        cmd = parts[1]

        # 帮助
        if cmd == "help":
            help_msg = """🎴 日麻记录助手使用说明

【对局】
↓ 创建对局
/mj new
↓ 加入/修正对局结算
/mj 对局ID 分数
示例：/mj 19 25000

【查询】
↓ 查看进行中的对局
/mj list       
↓ 查看指定对局（可查看历史 + 役满）
/mj view 对局ID 
↓ 删除进行中的对局（仅创建者/管理员）
/mj delete 对局ID
↓ 查看役满图片
/mj view-yakuman 役满ID

【数据统计】
↓ 查看玩家战绩（不填则为自己）
/mj stats [QQ号/昵称]
↓ 查看役满统计（不填则为自己）
/mj ym-stats [QQ号/昵称]

【排行榜】
↓ 查看综合排行榜（可选类型：power/yk/top/iron）
/mj rank [power|yakuman|top|iron]

【数据可视化】
↓ 查看该玩家的分数趋势图
/mj chart 玩家名 

【役满记录】✨
↓ 创建新役满记录
/mj ym 对局ID 牌型   
↓ 修改役满牌型       
/mj ym 役满ID 牌型   
↓ 修改役满图片       
/mj ym img 役满ID    
（发送役满图片时，30 秒内自动绑定；超时需重新下指令）

【其他】
_(:з」∠)_你猜

↓ 显示本帮助
/mj help        
💡 提示：结算前可重复输入修正自己的分数"""
            yield event.plain_result(help_msg)
            return

        # 对局相关命令：new / 数字 / list / view
        if cmd in ("new", "list", "view") or re.match(r'^\d+$', cmd):
            async for result in self._handle_game_command(event, parts):
                yield result
            return

        # 查看役满图片
        if cmd == "view-yakuman":
            if len(parts) != 3:
                yield event.plain_result("❌ 格式错误！\n正确格式：/mj view-yakuman 役满ID")
                return
            yakuman_id = parts[2]
            success, result = await self.view_yakuman(event, yakuman_id)
            if success:
                yield event.image_result(result)
            else:
                yield event.plain_result(result)
            return

        # 删除对局（仅创建者或管理员可用）
        if cmd == "delete":
            if len(parts) != 3:
                yield event.plain_result("❌ 格式错误！\n正确格式：/mj delete 对局ID")
                return
            session_id = parts[2]

            # 仅允许删除正在进行中的对局
            session = self.session_manager.get_session(session_id)
            if not session:
                # 检查是否已经结算记录在案
                records = self.data_manager.load_records()
                if any(str(r.get("session_id")) == str(session_id) for r in records):
                    yield event.plain_result(f"❌ 对局 {session_id} 已结算，不能删除")
                    return
                yield event.plain_result(f"❌ 对局 {session_id} 不存在或已过期")
                return

            sender = event.get_sender_id()
            if sender != session.get('created_by') and not self._is_admin(event):
                yield event.plain_result("❌ 只有对局创建者或管理员才能删除该对局")
                return

            self.session_manager.remove_session(session_id)
            yield event.plain_result(f"✅ 对局 {session_id} 已删除")
            return

        # 个人战绩统计
        if cmd == "stats":
            identifier = parts[2] if len(parts) >= 3 else ""
            async for result in self.handle_stats(event, identifier):
                yield result
            return

        # 役满统计
        if cmd == "ym-stats":
            identifier = parts[2] if len(parts) >= 3 else ""
            async for result in self.handle_ym_stats(event, identifier):
                yield result
            return

        # 排行榜
        if cmd == "rank":
            board_type = parts[1] if len(parts) >= 2 else "power"
            async for result in self.handle_rank(event, board_type):
                yield result
            return

        # 图表命令
        if cmd == "chart":
            if len(parts) != 2 and len(parts) != 3:
                yield event.plain_result("❌ 格式错误！\n正确格式：/mj chart 玩家名")
                return
            async for result in self.handle_chart(event):
                yield result
            return

        # 役满命令
        if cmd == "ym":
            async for result in self.yakuman_mgr.handle_command(event, parts):
                yield result
            return

        # 趣味关系
        if cmd in ("love", "hate"):
            async for result in self.handle_love_hate(event, cmd):
                yield result
            return

        yield event.plain_result("❌ 未知命令，使用 /mj help 查看帮助")

    async def _handle_game_command(self, event: AstrMessageEvent, parts: list[str]):
        """处理 /mj new、/mj <id>、/mj list、/mj view 等对局相关命令。"""
        cmd = parts[1]
        # 直接复用原有 GameHandler 逻辑
        async for result in self.game_handler.handle(event, parts):
            yield result

    def _bar(self, value: float, max_value: float, width: int = 10) -> str:
        """简单文本条形图（用于展示分布/频率）。"""
        if max_value <= 0:
            return "".ljust(width)
        filled = int(min(1.0, max(0.0, value / max_value)) * width)
        return "█" * filled + "░" * (width - filled)

    async def handle_stats(self, event: AstrMessageEvent, identifier: str):
        # 如果没有传参，优先使用昵称再 fallback 为 QQ
        candidates = []
        if identifier:
            candidates = [identifier]
        else:
            nick = event.get_sender_name() or ""
            if nick:
                candidates.append(nick)
            candidates.append(event.get_sender_id())

        stats = {}
        for cand in candidates:
            stats = self.stats_mgr.calc_player_stats(cand)
            if stats:
                identifier = cand
                break

        if not stats:
            yield event.plain_result("❌ 未找到该玩家的结算记录，请确认 QQ/昵称 是否正确")
            return

        nickname = self.get_nickname(event) if identifier == event.get_sender_id() else identifier
        msg = [f"🀄 玩家 {nickname} 战绩分析"]
        msg.append("📊 基础数据")
        msg.append(f"总对局: {stats['total_games']} | 平均顺位: {stats['avg_rank']}")
        msg.append(
            f"1位: {stats['rank_counts'][1]} ({stats['rank_rates'][1]}%) | "
            f"2位: {stats['rank_counts'][2]} ({stats['rank_rates'][2]}%) | "
            f"3位: {stats['rank_counts'][3]} ({stats['rank_rates'][3]}%) | "
            f"4位: {stats['rank_counts'][4]} ({stats['rank_rates'][4]}%)"
        )
        msg.append("📈 近期走势 (近10局)")
        trend = " → ".join(str(r) for r in stats['recent_trend'])
        msg.append(trend or "暂无")
        msg.append(f"实力分: {stats['rating_score']}")
        msg.append(f"平均分差: {stats['avg_diff']} 点")
        if stats['best']:
            msg.append(f"🏆 最高分: {stats['best'][1]} (对局 {stats['best'][0]})")
        if stats['worst']:
            msg.append(f"💥 最低分: {stats['worst'][1]} (对局 {stats['worst'][0]})")

        yield event.plain_result("\n".join(msg))

    async def handle_ym_stats(self, event: AstrMessageEvent, identifier: str):
        if not identifier:
            identifier = event.get_sender_id()
        stats = self.stats_mgr.get_yakuman_stats(identifier)
        if stats.get("total_yakuman", 0) == 0:
            yield event.plain_result("🎭 目前未找到该玩家的役满记录")
            return

        total_games = self.stats_mgr.get_player_records(identifier)
        total_games = len(total_games)
        nickname = self.get_nickname(event) if identifier == event.get_sender_id() else identifier
        msg = [f"🌟 [{nickname}] 役满殿堂"]
        msg.append(f"🔸 役满总数: {stats['total_yakuman']} (密度: {stats['density']}%)")
        msg.append("🧾 牌型分布：")
        max_count = max(stats['distribution'].values()) if stats['distribution'] else 0
        for yak_type, count in stats['distribution'].items():
            bar = self._bar(count, max_count, width=10)
            msg.append(f"{yak_type}: {count} {bar}")

        with_image_count = len(stats['with_image'])
        msg.append(f"🖼️ 已存档图片: {with_image_count}/{stats['total_yakuman']}")
        msg.append("最近的役满：")
        for y in stats['recent']:
            mark = "★" if y.get("is_double") else ""
            msg.append(
                f"[{y.get('type')}] {mark} ID: {y.get('id')} -> /mj view-yakuman {y.get('id')}"
            )

        yield event.plain_result("\n".join(msg))

    async def handle_rank(self, event: AstrMessageEvent, board_type: str):
        board_type = board_type.lower()
        mapping = {
            "power": "综合实力榜",
            "yakuman": "欧皇榜",
            "top": "常胜将军榜",
            "iron": "铁人榜",
        }
        title = mapping.get(board_type, "综合实力榜")

        leaderboard = self.stats_mgr.get_leaderboard(board_type)
        if not leaderboard:
            yield event.plain_result("❌ 当前没有足够数据生成排行榜")
            return

        msg = [f"🏆 {title}（前{len(leaderboard)}名）"]
        prev_value = None
        for idx, p in enumerate(leaderboard, start=1):
            if board_type == "power":
                value = p.get("power_score_avg", 0)
                suffix = f"实力分: {value}"
            elif board_type == "yakuman":
                value = p.get("yakuman", 0)
                suffix = f"役满: {value}"
            elif board_type == "top":
                value = p.get("top_rate", 0)
                suffix = f"TOP率: {value}%"
            else:
                value = p.get("games", 0)
                suffix = f"对局: {value}"

            diff = ""
            if prev_value is not None:
                diff_val = round(prev_value - value, 2)
                if diff_val != 0:
                    diff = f" (差 {diff_val})"
            prev_value = value
            msg.append(f"{idx}. {p.get('nickname') or p.get('qq')} - {suffix}{diff}")

        yield event.plain_result("\n".join(msg))

    async def handle_love_hate(self, event: AstrMessageEvent, cmd: str):
        identifier = event.get_sender_id()
        target = self.stats_mgr.get_love_hate(identifier, cmd)
        if not target:
            yield event.plain_result("❌ 无足够数据计算缘分关系")
            return
        if cmd == "love":
            yield event.plain_result(f"💗 你吃1时，最常吃4的人是：{target}")
        else:
            yield event.plain_result(f"💔 你吃4时，最常吃1的人是：{target}")

    async def view_yakuman(self, event: AstrMessageEvent, yakuman_id: str):
        """查看指定役满的牌型图片"""
        result = self.yakuman_mgr.find_yakuman(yakuman_id)
        if not result:
            return False, f"❌ 役满ID {yakuman_id} 不存在"

        image_path = self.yakuman_mgr.get_yakuman_image_path(yakuman_id)
        if not image_path:
            return False, f"❌ 该役满（{yakuman_id}）暂无图片，请使用 /mj ym img {yakuman_id} 上传"

        return True, str(image_path)

    async def handle_image(self, event: AstrMessageEvent, html_render):
        """处理图片消息（在 YakumanManager 中自行筛选是否需要处理）"""
        async for result in self.yakuman_mgr.handle_image_upload(event, html_render):
            yield result
