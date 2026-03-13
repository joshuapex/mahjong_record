import json
from pathlib import Path
from typing import Dict, List
from datetime import datetime, timedelta


class DataManager:
    """数据管理类 - 负责所有文件的读写"""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.data_path = base_path / "data"
        self.sessions_file = self.data_path / "sessions.json"
        self.records_file = self.data_path / "records.json"
        self.counter_file = self.data_path / "counter.txt"

        self._ensure_files()

    def _ensure_files(self):
        self.data_path.mkdir(exist_ok=True)
        if not self.sessions_file.exists():
            with open(self.sessions_file, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False, indent=2)
        if not self.records_file.exists():
            with open(self.records_file, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
        if not self.counter_file.exists():
            with open(self.counter_file, 'w') as f:
                f.write("1")

    # 会话相关
    def load_sessions(self) -> Dict:
        try:
            with open(self.sessions_file, 'r', encoding='utf-8') as f:
                sessions = json.load(f)
            now = datetime.now()
            valid = {}
            for sid, session in sessions.items():
                created_at = datetime.fromisoformat(session['created_at'])
                if now - created_at < timedelta(hours=2):
                    valid[sid] = session
            return valid
        except:
            return {}

    def save_sessions(self, sessions: Dict):
        with open(self.sessions_file, 'w', encoding='utf-8') as f:
            json.dump(sessions, f, ensure_ascii=False, indent=2)

    # 计数器
    def load_counter(self) -> int:
        try:
            with open(self.counter_file, 'r') as f:
                return int(f.read().strip())
        except:
            return 1

    def save_counter(self, counter: int):
        with open(self.counter_file, 'w') as f:
            f.write(str(counter))

    # 历史记录
    def load_records(self) -> List:
        try:
            with open(self.records_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []

    def save_record(self, record: Dict):
        records = self.load_records()
        records.append(record)
        with open(self.records_file, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)