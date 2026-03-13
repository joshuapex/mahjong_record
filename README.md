# mahjong_record

一个基于 AstrBot 的“日麻对局记录 + 数据统计 + 役满管理”插件。

## ✅ 功能概览

- **对局结算**（轻量版）：通过 `/mj new` + `/mj <id> <分数>` 快速录入对局结果。
- **对局查询**：查看进行中对局、历史结算结果、役满详情。
- **战绩统计**：个人战绩分析（总局数、平均顺位、最近趋势、实力分、最高/最低等）。
- **役满管理**：创建/更新役满记录，并支持上传图片查看。
- **排行榜 & 可视化**：生成实力榜、TOP率榜、分数趋势图等。

## 🧩 目录结构

```
mahjong_record/
├── __init__.py
├── metadata.yaml        # 插件元数据
├── main.py              # 插件入口、路由与注册
├── core/                # 核心逻辑模块
│   ├── session.py       # 对局（session）管理
│   ├── data_manager.py  # 文件读写（JSON 存储）
│   ├── game_handler.py  # /mj 对局相关操作（新建/报分/查询）
│   ├── mj_router.py     # /mj 命令路由与处理
│   ├── stats.py         # 战绩统计逻辑
│   └── yakuman.py       # 役满记录逻辑
└── visualization/       # 图表生成模块
    ├── chart_generator.py
    └── templates/       # HTML 模板
        ├── player_chart.html
        └── rank_chart.html
```

## 🚀 安装 / 使用方式（AstrBot 插件）

1. 把本项目放入 AstrBot 插件目录（或按 AstrBot 要求安装）。
2. 启动 AstrBot，插件会自动注册命令 `/mj`。

## 🧠 支持的命令

### 对局操作
- `/mj new`：创建一个新对局（生成对局ID）。
- `/mj <id> <分数>`：加入/更新当前对局中你的分数。
- `/mj list`：查看所有正在进行中的对局。
- `/mj view <id>`：查看指定对局（进行中/已结算）。
- `/mj delete <id>`：删除进行中的对局（仅对局创建者或管理员可用）。

### 数据查询
- `/mj stats [QQ/昵称]`：查询个人战绩（默认当前用户）。
- `/mj ym-stats [QQ/昵称]`：查询个人役满统计（默认当前用户）。
- `/mj rank [power|yakuman|top|iron]`：查看排行榜。
- `/mj chart <玩家名>`：生成该玩家分数趋势图。

### 役满管理
- `/mj ym <对局ID> <牌型>`：创建役满记录。
- `/mj ym <役满ID> <牌型>`：修改役满牌型。
- `/mj ym img <役满ID>`：修改役满图片（发送图片后 30 秒内自动绑定）。
- `/mj view-yakuman <役满ID>`：查看役满图片。

### 帮助
- `/mj help`：查看帮助信息。

## 🔐 管理员配置（可选）

如果你希望让某些 QQ 号拥有管理员权限（例如能删除他人对局），请设置环境变量：

```bash
export MJ_ADMIN_IDS="123456,789012"
```

> Windows PowerShell:
> ```powershell
> $env:MJ_ADMIN_IDS = "123456,789012"
> ```

插件会自动识别 AstrBot 事件中的管理员/群主标记（若框架支持），并在无法识别时回退到上述环境变量列表。

## 🧰 运行时存储

- `data/sessions.json`：进行中对局（仅保留 2 小时内的会话）
- `data/records.json`：已结算对局记录
- `data/counter.txt`：对局 ID 计数器

---

如有功能需求或错误反馈，欢迎提 issue。

其实以上都是花了一天时间让AI生成的，我压根不会python，别骂了喵别骂了喵。

功能测过的也没几个，就基本功能能用，但自己还没和小伙伴们线下试过。

BUG有缘再改，功能有缘再补【心虚】