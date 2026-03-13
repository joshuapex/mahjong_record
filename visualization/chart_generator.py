import json
from pathlib import Path
from typing import Dict, List, Tuple

from astrbot.api import logger


class ChartGenerator:
    """图表生成类"""

    def __init__(self, data_manager, base_path: Path):
        self.data_manager = data_manager
        self.template_path = base_path / "visualization" / "templates"

    async def generate_player_chart(self, html_render_func, player_name: str) -> Tuple[bool, str]:
        """生成玩家分数趋势图"""
        records = self.data_manager.load_records()

        player_sessions = []
        for record in records:
            for player in record['players']:
                if player['nickname'] == player_name:
                    player_sessions.append({
                        'time': record['settle_time'][5:10],
                        'score': player['score'],
                    })
                    break

        if len(player_sessions) < 2:
            return False, f"📊 玩家 {player_name} 的对局记录不足（至少需要2局）"

        dates = [s['time'] for s in player_sessions[-10:]]
        scores = [s['score'] for s in player_sessions[-10:]]
        avg_score = round(sum(scores) / len(scores))
        best_score = max(scores)
        worst_score = min(scores)

        template_file = self.template_path / "player_chart.html"
        if not template_file.exists():
            return False, "❌ 图表模板文件不存在"

        html_template = template_file.read_text(encoding='utf-8')
        render_data = {
            'player_name': player_name,
            'count': len(scores),
            'dates': dates,
            'scores': scores,
            'avg_score': avg_score,
            'best_score': best_score,
            'worst_score': worst_score
        }

        try:
            img_url = await html_render_func(html_template, render_data)
            return True, img_url
        except Exception as e:
            logger.error(f"生成图表失败: {e}")
            return False, "❌ 图表生成失败，请稍后重试"

    async def generate_rank_chart(self, html_render_func) -> Tuple[bool, str]:
        """生成全体玩家顺位分布图"""
        records = self.data_manager.load_records()
        if not records:
            return False, "📊 暂无对局记录"

        player_stats = {}
        for record in records:
            for player in record['players']:
                nickname = player['nickname']
                if nickname not in player_stats:
                    player_stats[nickname] = {'total': 0, 'rank1': 0, 'rank2': 0, 'rank3': 0, 'rank4': 0}
            for r in record['rankings']:
                nickname = r['nickname']
                player_stats[nickname]['total'] += 1
                player_stats[nickname][f'rank{r["rank"]}'] += 1

        sorted_players = sorted(player_stats.items(), key=lambda x: x[1]['total'], reverse=True)[:8]
        if not sorted_players:
            return False, "📊 暂无统计数据"

        players = [p[0] for p in sorted_players]
        rank1 = [p[1]['rank1'] for p in sorted_players]
        rank2 = [p[1]['rank2'] for p in sorted_players]
        rank3 = [p[1]['rank3'] for p in sorted_players]
        rank4 = [p[1]['rank4'] for p in sorted_players]

        template_file = self.template_path / "rank_chart.html"
        if not template_file.exists():
            return False, "❌ 图表模板文件不存在"

        html_template = template_file.read_text(encoding='utf-8')
        total_games = len(records)
        render_data = {
            'players': players,
            'rank1': rank1,
            'rank2': rank2,
            'rank3': rank3,
            'rank4': rank4,
            'total_games': total_games,
            'player_count': len(player_stats)
        }

        try:
            img_url = await html_render_func(html_template, render_data)
            return True, img_url
        except Exception as e:
            logger.error(f"生成图表失败: {e}")
            return False, "❌ 图表生成失败，请稍后重试"