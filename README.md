# DeepseekBrowserScript

> 基于 Playwright 浏览器自动化的 AI 编码代理框架。通过浏览器与 DeepSeek 对话，让 AI 直接操作文件系统、执行 Shell 命令、收发 QQ 消息、控制浏览器页面。**无需 API 密钥**。

---

## 特性

- **AI 驱动** – DeepSeek 自主规划任务并调用工具完成复杂工作流
- **完整的文件系统操作** – 读写、搜索、替换、批量处理、目录遍历
- **Shell 命令执行** – 支持前台/后台运行，进程树管理，超时强杀
- **QQ 机器人集成** – 监听群消息、发送消息，支持 @ 和关键词触发
- **浏览器自动化** – 导航、点击、填表、JS 注入、DOM 快照、多标签页管理
- **扩展工具** – 五子棋等扩展可通过 `--ext-tools` 按需加载
- **持久化会话** – 浏览器登录状态保存在本地，一次登录自动复用
- **分层配置** – 默认配置 + 用户全局配置 + 项目配置，逐层覆盖
- **完整日志系统** – 控制台彩色输出 + 文件日志自动滚动归档
- **交互模式** – REPL 式输入，支持切换对话和实时任务输入
- **测试验证** – `run_test` 工具执行验证脚本，判断任务是否完成
- **工具调用解析** – 自动从 AI 响应中提取 `tool_call` JSON 并执行

---

## 安装

```bash
# 克隆仓库
git clone https://github.com/your-name/DeepseekBrowserScript.git
cd DeepseekBrowserScript

# 安装依赖
pip install playwright requests

# 安装 Playwright 浏览器（首次运行需要）
playwright install chromium
```

**环境要求**：Python 3.8+

---

## 配置

配置加载顺序：**默认配置 → 全局配置 → 项目配置**（后者覆盖前者）。

所有配置项都有默认值，无配置文件也能直接运行。

### 全局配置（可选）
路径：`~/.deepseek-agent/config.json`

适合存放个人敏感信息（如 QQ 机器人地址），该目录不会被 Git 追踪。

```json
{
  "QQ_API_HOST": "192.168.1.100",
  "QQ_API_PORT": 3000,
  "HEADLESS": true,
  "MODE": "expert"
}
```

### 项目配置（可选）
路径：项目根目录 `ds-agent-config.json`

适合存放项目专属配置（如工作目录、测试脚本）。

```json
{
  "WORKING_DIR": "/home/user/my_project",
  "TEST_BAT_PATH": "./test.bat",
  "MAX_ITERATIONS": 200
}
```

### 完整配置项

| 键                   | 类型     | 默认值                         | 说明                                       |
|---------------------|--------|-----------------------------|------------------------------------------|
| `DEEPSEEK_URL`      | string | `https://chat.deepseek.com` | DeepSeek 聊天页面 URL                        |
| `SESSION_DIR`       | string | `./session/session`         | 浏览器用户数据目录                                |
| `HEADLESS`          | bool   | `False`                     | 是否无头模式运行浏览器                              |
| `RESPONSE_TIMEOUT`  | int    | `1000000`                   | 等待 AI 响应超时（毫秒）                           |
| `STABLE_DELAY`      | int    | `10000`                     | 响应稳定判定延迟（毫秒）                             |
| `SEND_DELAY`        | int    | `400`                       | 发送消息后延迟（毫秒）                              |
| `MAX_ITERATIONS`    | int    | `300`                       | 最大工具调用循环次数                               |
| `WORKING_DIR`       | string | 当前目录                        | 默认工作目录                                   |
| `MAX_OUTPUT_LENGTH` | int    | `8000`                      | 工具输出截断长度                                 |
| `DEBUG`             | bool   | `False`                     | 是否输出调试信息                                 |
| `MODE`              | string | `fast`                      | DeepSeek 模式：`fast` / `expert` / `vision` |
| `QQ_API_HOST`       | string | `""`                        | QQ API 地址，留空则不加载 QQ 工具                   |
| `QQ_API_PORT`       | int    | `3000`                      | QQ API 端口                                |
| `QQ_POLL_TIMEOUT`   | int    | `180`                       | QQ 监听超时（分钟）                              |
| `QQ_POLL_INTERVAL`  | int    | `5`                         | QQ 轮询间隔（秒）                               |
| `TEST_BAT_PATH`     | string | `None`                      | 测试脚本路径                                   |

---

## 使用方法

```bash
python -m ds [选项] [任务]
```

### 命令行选项

| 选项                            | 说明                                |
|-------------------------------|-----------------------------------|
| `-t, --task TEXT`             | 直接指定任务文本                          |
| `-i, --interactive`           | 进入交互式 REPL 模式                     |
| `-d, --dir PATH`              | 设置工作目录                            |
| `--debug`                     | 输出详细调试信息                          |
| `--headless`                  | 无头模式运行浏览器                         |
| `--mode {fast,expert,vision}` | 切换 DeepSeek 模型模式                  |
| `--session-dir NAME`          | 指定会话目录名（默认 `main`），用于隔离不同任务的浏览器状态 |
| `--test-bat PATH`             | 指定测试脚本路径                          |
| `--max-iterations N`          | 最大循环轮数                            |
| `--ext-tools wzq`             | 加载扩展工具（如五子棋）                      |
| `--deny-tools TOOL1 TOOL2`    | 禁用指定工具                            |
| `--task-path FILE`            | 从文件读取任务内容                         |
| `--load-file FILE`            | 启动时上传文件到 DeepSeek 聊天              |
| `--roll-name NAME`            | 归档日志文件名后缀                         |
| `--log-path PATH`             | 日志目录（默认 `./logs`）                 |

### 示例

```bash
# 直接执行任务
python -m ds -t "创建一个 Python 脚本，打印 Hello World"

# 交互模式（可连续输入多个任务）
python -m ds -i

# 指定工作目录和无头模式
python -m ds --dir ./my_project --headless -t "运行所有单元测试"

# 使用测试脚本验证任务完成
python -m ds --test-bat ./test.bat -t "修复所有 ESLint 错误"

# 加载五子棋扩展工具
python -m ds --ext-tools wzq -t "陪我下五子棋"

# 隔离不同项目的浏览器状态（会话目录独立）
python -m ds --session-dir project_a "构建前端项目"
python -m ds --session-dir project_b "构建后端项目"

# 从文件读取任务
python -m ds --task-path ./task.txt

# 上传文件到聊天上下文
python -m ds --load-file ./data.csv "分析这个 CSV 文件"
```

---

## 工具列表

AI 通过 `tool_call` 代码块调用工具。响应格式如下：

````markdown
```tool_call
{
  "tools": [
    { "name": "read_file", "args": { "path": "main.py" } },
    { "name": "write_file", "args": { "path": "out.txt", "content": "hello" } }
  ]
}
```
````

工具按顺序执行，若某个工具失败则停止后续调用。

---

### 文件操作工具

| 工具名                | 功能                      | 参数                                                                            |
|--------------------|-------------------------|-------------------------------------------------------------------------------|
| `read_file`        | 读取文件内容，支持按行号范围读取        | `path`(必填), `start_line`, `end_line`                                          |
| `write_file`       | 写入文件（覆盖），自动创建父目录        | `path`(必填), `content`(必填)                                                     |
| `append_to_file`   | 追加内容到文件末尾               | `path`(必填), `content`(必填)                                                     |
| `replace_in_file`  | 查找并替换文本，支持正则表达式         | `path`(必填), `find`(必填), `replace`(必填), `use_regex`, `all_occurrences`         |
| `delete_file`      | 永久删除文件                  | `path`(必填)                                                                    |
| `list_directory`   | 列出目录内容，支持递归             | `path`, `recursive`, `show_hidden`                                            |
| `create_directory` | 创建目录（含所有父目录）            | `path`(必填)                                                                    |
| `move_file`        | 移动或重命名文件/目录             | `source`(必填), `destination`(必填)                                               |
| `copy_file`        | 复制文件到新位置                | `source`(必填), `destination`(必填)                                               |
| `get_file_info`    | 获取文件/目录元数据（大小、修改时间、行数等） | `path`(必填)                                                                    |
| `find_files`       | 按 glob 模式搜索文件名          | `pattern`(必填), `directory`, `exclude`                                         |
| `search_in_files`  | 在文件内容中搜索文本（类似 grep -r）  | `pattern`(必填), `directory`, `file_pattern`, `case_sensitive`, `context_lines` |
| `write_files`      | 批量写入多个文件                | `files`(必填, `[{path, content}]`)                                              |

---

### 命令执行工具

| 工具名           | 功能                                     | 参数                                             |
|---------------|----------------------------------------|------------------------------------------------|
| `run_command` | 执行 Shell 命令。`wait=False` 时后台运行，立即返回    | `command`(必填), `cwd`, `timeout`, `env`, `wait` |
| `run_test`    | 运行测试脚本（由 `TEST_BAT_PATH` 指定）。测试通过则任务完成 | 无                                              |
| `abort_task`  | 强制中止任务                                 | `reason`(必填), `errorCode`(必填)                  |

**`run_command` 特性**：
- `wait=True`（默认）：等待命令结束，返回 stdout/stderr，超时则强制终止进程树
- `wait=False`：命令后台运行，返回 PID；Windows 使用 Job Object 确保父进程退出时子进程被清理
- Windows 下自动修复 `start /B` 命令的标题参数问题

---

### QQ 机器人工具（需配置 `QQ_API_HOST`）

依赖外部 HTTP API 服务（如 go-cqhttp），通过 `QQ_API_HOST` 和 `QQ_API_PORT` 连接。

| 工具名 | 功能 | 参数 |
|---|---|---|
| `listen_group_msg` | 监听群消息，阻塞直到触发条件满足或超时 | `group_id`(必填), `trigger`, `keyword`, `timeout`, `history_limit`, `fetch_count`, `trigger_count` |
| `send_group_msg` | 发送消息并立即监听回复 | `group_id`(必填), `text`(必填), `at_user`, `trigger`, `keyword`, `timeout`, `history_limit`, `fetch_count`, `trigger_count` |

**触发类型**：
- `any`：任意群消息触发
- `mention`：被 @ 时触发
- `keyword`：包含指定关键词时触发

**`trigger_count`**：累计触发次数达到该值才返回，默认 1。

---

### 浏览器自动化工具

浏览器子进程独立运行，支持多标签页管理。

| 工具名                     | 功能                              | 参数                                                                         |
|-------------------------|---------------------------------|----------------------------------------------------------------------------|
| `browser_navigate`      | 导航到指定 URL                       | `url`(必填), `timeout`                                                       |
| `browser_execute_js`    | 执行 JavaScript，可保存为可复用脚本         | `js_code`(必填), `save_as`, `timeout`, `args`                                |
| `browser_run_saved_js`  | 运行已保存的 JS 脚本                    | `name`(必填), `timeout`, `args`                                              |
| `browser_json_snapshot` | 获取 DOM 树 JSON 快照，支持属性过滤         | `max_depth`, `max_children`, `max_nodes`, `include_attrs`, `exclude_attrs` |
| `browser_get_html`      | 获取当前页面完整 HTML 源码                | 无                                                                          |
| `browser_click`         | 点击元素（CSS 选择器或 ref 编号如 `E1`）     | `target`(必填), `by_ref`                                                     |
| `browser_fill`          | 向输入框填充文本                        | `target`(必填), `text`(必填), `by_ref`                                         |
| `browser_hover`         | 悬停到指定元素                         | `target`(必填), `by_ref`                                                     |
| `browser_scroll`        | 滚动页面到指定坐标                       | `x`(必填), `y`(必填)                                                           |
| `browser_get_page_info` | 获取当前页面标题和 URL                   | 无                                                                          |
| `browser_clear_session` | 清空浏览器会话（cookies、localStorage 等） | 无                                                                          |
| `browser_new_page`      | 创建新标签页，可选导航到 URL                | `url`                                                                      |
| `browser_close_page`    | 关闭指定 ID 的标签页（不能关闭最后一个）          | `page_id`(必填)                                                              |
| `browser_switch_page`   | 切换到指定 ID 的标签页                   | `page_id`(必填)                                                              |
| `browser_list_pages`    | 列出所有打开的标签页（ID、标题、URL）           | 无                                                                          |

**`browser_json_snapshot` 属性过滤**：
- 传入 `include_attrs`：只保留指定属性（白名单）
- 不传则按 `exclude_attrs` 排除（默认排除 `style`）
- 属性名支持通配符 `*`，如 `on*` 匹配所有 `onclick`、`onchange` 等

---

### 扩展工具（需 `--ext-tools wzq`）

| 工具名                           | 功能                                     | 参数                         |
|-------------------------------|----------------------------------------|----------------------------|
| `huliqin_wzq_get_board`       | 获取五子棋棋盘状态 + 棋型分析（活二/活三/眠三/冲四/活四/威胁点）   | 无                          |
| `huliqin_wzq_drop_stone`      | 落子，坐标支持 `"A1"~"O15"` 或 `"1,1"~"15,15"` | `pos`(必填)                  |
| `huliqin_wzq_join_seat`       | 加入座位（0 或 1），已被占用则返回成功                  | `seat`                     |
| `huliqin_wzq_get_room_status` | 获取房间信息（房间号、玩家、我的座位/颜色、游戏是否开始）          | 无                          |
| `huliqin_wzq_wait_my_turn`    | 阻塞等待轮到己方回合，超时返回失败                      | `timeout`, `poll_interval` |

---

## 日志

- **控制台输出**：彩色日志，包含步骤、工具调用、结果
- **文件日志**：
  - `logs/latest.log` – 本次运行日志（每次启动清空）
  - `logs/YYYY-MM-DD/YYYY-MM-DD-XXXX-{roll_name}.log` – 按日期和索引自动归档
- `--debug` 输出更详细的信息
- `--roll-name` 指定归档文件名后缀

---

## 项目结构

```
ds/
├── __main__.py          # 入口，解析命令行参数
├── agent.py             # DeepSeekAgent 主循环
├── browser.py           # 浏览器控制（Playwright）
├── config.py            # 配置加载（默认 + 全局 + 项目）
├── logger.py            # 日志系统
├── prompt.py            # 系统提示词 + 对话历史管理
├── get_prompt_texts.js  # 页面提示文本提取 JS
├── agentTools/
│   ├── __init__.py      # TOOLS 注册表
│   ├── file.py          # 文件操作工具（13 个）
│   ├── task.py          # 命令执行 / 测试 / 中止
│   ├── qqbot.py         # QQ 机器人工具
│   └── broswer/
│       ├── browser.py         # 浏览器工具封装
│       ├── browser_client.py  # 客户端代理（多进程通信）
│       ├── browser_service.py # 浏览器子进程服务
│       ├── dom_snapshot.js    # DOM 快照 JS
│       └── gameHullqin/
│           ├── __init__.py    # 扩展工具加载
│           ├── wzq.py         # 五子棋工具（6 个）
│           └── wzq_analyze.py # 棋型分析（活二/活三/冲四等）
```

---

## 常见问题

### 1. 浏览器显示“需要登录”
首次运行请手动登录 DeepSeek 账号，登录状态保存在 `SESSION_DIR` 中。若登录失效，删除该目录重试。

### 2. QQ 工具未加载
`QQ_API_HOST` 默认为空，需在全局配置或项目配置中设置有效 IP/域名。启动时会输出警告，但不影响其他工具。

### 3. AI 不调用工具或输出格式错误
确保 AI 响应中包含正确的 `tool_call` JSON 代码块。解析错误时，代理会自动发送修复提示。

### 4. 浏览器操作超时
调整 `RESPONSE_TIMEOUT` 和 `STABLE_DELAY` 配置，或为特定 `browser_navigate` 增加 `timeout` 参数。

### 5. 后台进程未清理（Windows）
`run_command` 的 `wait=False` 模式会自动将进程加入 Job Object，父进程退出时由系统自动清理。同时 `atexit` 注册了后备清理逻辑。

### 6. 对话达到长度限制
DeepSeek 对话有长度上限，遇到时需手动开启新对话（交互模式输入 `new` 命令）。

---

## 许可证

MIT License

Copyright (c) 2026 Wu_RH

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
