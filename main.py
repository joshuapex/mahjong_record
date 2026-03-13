import os
from pathlib import Path

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

from .core.data_manager import DataManager
from .core.session import SessionManager
from .core.yakuman import YakumanManager
from .core.stats import StatsManager
from .core.game_handler import GameHandler
from .core.mj_router import MJCommandRouter
from .visualization.chart_generator import ChartGenerator


@register("mahjong_record", "麻将对局记录", "极简指令的麻将对局结算 + 数据可视化 + 役满记录", "3.0.0")
class MahjongRecordPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.base_path = Path(__file__).parent

        # 初始化各个模块
        self.data_manager = DataManager(self.base_path)
        self.session_manager = SessionManager(self.data_manager)
        self.chart_generator = ChartGenerator(self.data_manager, self.base_path)
        self.yakuman_mgr = YakumanManager(self.base_path, self.data_manager, self._get_nickname)
        self.game_handler = GameHandler(self.data_manager, self.session_manager, self._get_nickname)
        self.stats_mgr = StatsManager(self.data_manager)
        admin_ids_env = os.getenv("MJ_ADMIN_IDS", "")
        admin_ids = [x.strip() for x in admin_ids_env.split(",") if x.strip()]

        self.router = MJCommandRouter(
            self.data_manager,
            self.session_manager,
            self.chart_generator,
            self.yakuman_mgr,
            self.stats_mgr,
            self.game_handler,
            self.html_render,
            self._get_nickname,
            admin_ids=admin_ids,
        )

    def _get_nickname(self, event: AstrMessageEvent) -> str:
        """获取发送者的昵称"""
        try:
            return event.get_sender_name() or f"玩家{event.get_sender_id()[-4:]}"
        except:
            return f"玩家{event.get_sender_id()[-4:]}"

    @filter.command("mj")
    async def mj_command(self, event: AstrMessageEvent):
        """主命令处理（转发给路由器）。"""
        async for result in self.router.handle_mj_command(event):
            yield result

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_image(self, event: AstrMessageEvent):
        """处理图片消息（转发给路由器）。"""
        async for result in self.router.handle_image(event, self.html_render):
            yield result

    @filter.command("mj_chart")
    async def mj_chart(self, event: AstrMessageEvent):
        """生成指定玩家的分数趋势图（转发给路由器）。"""
        async for result in self.router.handle_chart(event):
            yield result

    @filter.command("mj_rank")
    async def mj_rank(self, event: AstrMessageEvent):
        """生成全体玩家的顺位分布统计（转发给路由器）。"""
        async for result in self.router.handle_rank(event, "power"):
            yield result

    async def terminate(self):
        self.session_manager.save_all()
        self.yakuman_mgr.pending.clear()
        logger.info("麻将插件已卸载")