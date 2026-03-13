import re
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

import aiohttp

from astrbot.api import logger

# 役满牌型映射（番数）
YAKUMAN_TYPES = {
    "四暗刻": 13,
    "国士无双": 13,
    "九莲宝灯": 13,
    "大三元": 13,
    "小四喜": 13,
    "大四喜": 26,
    "字一色": 13,
    "绿一色": 13,
    "清老头": 13,
    "地和": 13,
    "天和": 13,
    "四暗刻单骑": 26,
    "纯正九莲宝灯": 26,
    "四杠子": 26,
}


class YakumanManager:
    """役满管理类 - 处理所有役满相关命令"""

    def __init__(self, base_path: Path, data_manager, get_nickname_func):
        self.base_path = base_path
        self.data_manager = data_manager
        self.get_nickname = get_nickname_func
        self.yakuman_dir = base_path / "data" / "yakuman"
        self.yakuman_dir.mkdir(parents=True, exist_ok=True)

        # 等待图片的临时状态 {qq: {...}}
        self.pending = {}

    def _load_records(self) -> list:
        return self.data_manager.load_records()

    def _save_records(self, records: list):
        with open(self.data_manager.records_file, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    def generate_yakuman_id(self, session_id: str, records: list) -> str:
        max_seq = 0
        for record in records:
            if record['session_id'] == session_id:
                for player in record['players']:
                    for yakuman in player.get('yakuman', []):
                        if yakuman['id'].startswith(f"{session_id}-"):
                            try:
                                seq = int(yakuman['id'].split('-')[1])
                                max_seq = max(max_seq, seq)
                            except:
                                pass
        return f"{session_id}-{max_seq + 1}"

    def get_yakuman_by_id(self, records: list, yakuman_id: str) -> Optional[Tuple[int, int, int, dict]]:
        for r_idx, record in enumerate(records):
            for p_idx, player in enumerate(record['players']):
                for y_idx, yakuman in enumerate(player.get('yakuman', [])):
                    if yakuman['id'] == yakuman_id:
                        return (r_idx, p_idx, y_idx, yakuman)
        return None

    def find_yakuman(self, yakuman_id: str) -> Optional[Tuple[int, int, int, dict]]:
        """查找指定役满记录（加载 records.json）。

        返回 (record_index, player_index, yakuman_index, yakuman_dict)，若不存在则返回 None。
        """
        records = self._load_records()
        return self.get_yakuman_by_id(records, yakuman_id)

    def save_yakuman_image(self, yakuman_id: str, image_data: bytes) -> str:
        filename = f"{yakuman_id}.jpg"
        file_path = self.yakuman_dir / filename
        file_path.write_bytes(image_data)
        return f"/data/yakuman/{filename}"

    def get_yakuman_image_path(self, yakuman_id: str) -> Optional[Path]:
        file_path = self.yakuman_dir / f"{yakuman_id}.jpg"
        return file_path if file_path.exists() else None

    async def handle_command(self, event, parts):
        """处理 /mj ym 子命令"""
        if len(parts) < 3:
            yield event.plain_result("❌ 格式错误！\n使用 /mj ym 对局ID 牌型 创建役满\n或 /mj ym 役满ID 牌型 修改役满\n或 /mj ym img 役满ID 修改图片")
            return

        subcmd_or_id = parts[2]
        qq = event.get_sender_id()
        nickname = self.get_nickname(event)

        # /mj ym img 役满ID
        if subcmd_or_id == "img":
            if len(parts) != 4:
                yield event.plain_result("❌ 格式错误！\n正确格式：/mj ym img 役满ID")
                return
            yakuman_id = parts[3]
            records = self._load_records()
            result = self.get_yakuman_by_id(records, yakuman_id)
            if not result:
                yield event.plain_result(f"❌ 役满ID {yakuman_id} 不存在")
                return
            r_idx, p_idx, y_idx, yakuman = result
            player = records[r_idx]['players'][p_idx]
            if player['qq'] != qq:
                yield event.plain_result(f"❌ 这不是你的役满记录，无法修改")
                return
            self.pending[qq] = {
                "yakuman_id": yakuman_id,
                "action": "update_img",
                "expire": datetime.now() + timedelta(seconds=30),
                "record_idx": r_idx,
                "player_idx": p_idx,
                "yakuman_idx": y_idx,
                "old_data": yakuman.copy()
            }
            yield event.plain_result(f"📸 请发送新的牌型图片（30秒内）")
            return

        # 修改役满牌型：役满ID格式
        if re.match(r'^\d+-\d+$', subcmd_or_id):
            if len(parts) < 4:
                yield event.plain_result("❌ 格式错误！\n正确格式：/mj ym 役满ID 牌型")
                return
            yakuman_id = subcmd_or_id
            new_type = parts[3]
            if new_type not in YAKUMAN_TYPES:
                valid_types = "、".join(list(YAKUMAN_TYPES.keys())[:10])
                yield event.plain_result(f"❌ 无效的役满牌型。常见牌型：{valid_types}...")
                return
            records = self._load_records()
            result = self.get_yakuman_by_id(records, yakuman_id)
            if not result:
                yield event.plain_result(f"❌ 役满ID {yakuman_id} 不存在")
                return
            r_idx, p_idx, y_idx, old_yakuman = result
            player = records[r_idx]['players'][p_idx]
            if player['qq'] != qq:
                yield event.plain_result(f"❌ 这不是你的役满记录，无法修改")
                return
            fan = YAKUMAN_TYPES[new_type]
            is_double = (fan == 26)
            old_yakuman['type'] = new_type
            old_yakuman['fan'] = fan
            old_yakuman['is_double'] = is_double
            old_yakuman['updated_at'] = datetime.now().isoformat()
            self._save_records(records)
            self.pending[qq] = {
                "yakuman_id": yakuman_id,
                "action": "update",
                "expire": datetime.now() + timedelta(seconds=30),
                "record_idx": r_idx,
                "player_idx": p_idx,
                "yakuman_idx": y_idx,
                "old_data": {"type": old_yakuman['type']}
            }
            msg = f"""✅ 役满牌型已更新！役满ID：{yakuman_id}
📸 是否要修改牌型图片？请在30秒内直接发送图片
（发送“跳过”保留原图）"""
            yield event.plain_result(msg)
            return

        # 新建役满：/mj ym 对局ID 牌型
        session_id = subcmd_or_id
        if len(parts) < 4:
            yield event.plain_result("❌ 格式错误！\n正确格式：/mj ym 对局ID 牌型")
            return
        yakuman_type = parts[3]
        if yakuman_type not in YAKUMAN_TYPES:
            valid_types = "、".join(list(YAKUMAN_TYPES.keys())[:10])
            yield event.plain_result(f"❌ 无效的役满牌型。常见牌型：{valid_types}...")
            return

        records = self._load_records()
        found = False
        for record in records:
            if record['session_id'] == session_id:
                for player in record['players']:
                    if player['qq'] == qq:
                        found = True
                        break
                break
        if not found:
            yield event.plain_result(f"❌ 你在对局 {session_id} 中没有报分记录，无法添加役满")
            return

        yakuman_id = self.generate_yakuman_id(session_id, records)
        fan = YAKUMAN_TYPES[yakuman_type]
        is_double = (fan == 26)
        yakuman_data = {
            "id": yakuman_id,
            "type": yakuman_type,
            "fan": fan,
            "is_double": is_double,
            "dora": 0,
            "uradora": 0,
            "round": "",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "image_url": None
        }

        for record in records:
            if record['session_id'] == session_id:
                for player in record['players']:
                    if player['qq'] == qq:
                        if 'yakuman' not in player:
                            player['yakuman'] = []
                        player['yakuman'].append(yakuman_data)
                        break
                break
        self._save_records(records)

        self.pending[qq] = {
            "yakuman_id": yakuman_id,
            "action": "create",
            "expire": datetime.now() + timedelta(seconds=30),
            "yakuman_data": yakuman_data
        }

        msg = f"""✅ 役满记录已创建！役满ID：{yakuman_id}
✨ 牌型：{yakuman_type} ({fan}番{f' 双倍役满' if is_double else ''})

📸 是否要保存牌型图片？请在30秒内直接发送图片
（发送“跳过”可略过）"""
        yield event.plain_result(msg)

    async def handle_skip(self, event):
        """处理 /skip 命令"""
        qq = event.get_sender_id()
        if qq not in self.pending:
            yield event.plain_result("❌ 当前没有等待上传的役满记录")
            return
        pending = self.pending[qq]
        yakuman_id = pending["yakuman_id"]
        del self.pending[qq]
        yield event.plain_result(f"✅ 役满ID {yakuman_id} 已保存（无图片）")

    async def handle_image_upload(self, event, html_render_func):
        """处理图片上传"""
        qq = event.get_sender_id()
        if qq not in self.pending:
            return

        pending = self.pending[qq]
        if datetime.now() > pending["expire"]:
            del self.pending[qq]
            yield event.plain_result("⏰ 图片上传超时，请重新发送指令")
            return

        # AstrBot v3: 使用 get_messages() 获取消息组件列表，然后从中筛选图片
        message_components = event.get_messages()
        image_components = [c for c in message_components if getattr(c, "type", "").lower() == "image"]
        # 如果这条消息里没有图片，直接忽略，让用户可以在 30 秒内自由聊天或重新发送图片
        if not image_components:
            return

        image_url = getattr(image_components[0], "url", None)
        if not image_url:
            yield event.plain_result("❌ 未检测到图片地址，请重新发送")
            return
        yakuman_id = pending["yakuman_id"]

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    if resp.status == 200:
                        image_data = await resp.read()
                        image_path = self.save_yakuman_image(yakuman_id, image_data)

                        records = self._load_records()
                        if pending["action"] in ("create", "update", "update_img"):
                            if pending["action"] == "create":
                                result = self.get_yakuman_by_id(records, yakuman_id)
                                if result:
                                    r_idx, p_idx, y_idx, yakuman = result
                                    yakuman['image_url'] = image_path
                                    yakuman['updated_at'] = datetime.now().isoformat()
                            else:
                                r_idx = pending["record_idx"]
                                p_idx = pending["player_idx"]
                                y_idx = pending["yakuman_idx"]
                                records[r_idx]['players'][p_idx]['yakuman'][y_idx]['image_url'] = image_path
                                records[r_idx]['players'][p_idx]['yakuman'][y_idx]['updated_at'] = datetime.now().isoformat()
                            self._save_records(records)

                        del self.pending[qq]
                        yield event.plain_result(f"✅ 图片已保存！役满ID：{yakuman_id}")
                        img_path = self.get_yakuman_image_path(yakuman_id)
                        if img_path:
                            yield event.image_result(str(img_path))
                    else:
                        yield event.plain_result("❌ 图片下载失败")
        except Exception as e:
            logger.error(f"处理图片失败: {e}")
            yield event.plain_result("❌ 图片处理失败，请重试")