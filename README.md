# Malice Network Python SDK

现代异步 Python 客户端库，用于 Malice Network C2 框架。

## 核心功能

- **异步编程** - 现代 Python async/await 支持
- **类型安全** - 完整的类型提示和 IDE 支持
- **动态 API** - 自动转发所有 133 个 gRPC 方法
- **mTLS 安全** - 安全的客户端身份验证
- **会话管理** - 自动会话上下文处理

## 安装

```bash
# 开发版本安装
git clone https://github.com/chainreactors/malice-network.git
cd malice-network/sdk/python
pip install -e .

# 生成协议文件
python generate.py
```

## 快速开始

### 30秒快速体验

```python
import asyncio
from IoM import MaliceClient
from IoM.proto.modulepb import Request

async def main():
    # 1. 连接服务器（需要 client.auth 文件）
    client = MaliceClient.from_config_file("client.auth")

    async with client:
        # 2. 获取会话
        await client.update_sessions()
        session_id = list(client.cached_sessions.keys())[0]
        session = await client.sessions.get_session(session_id)

        # 3. 执行命令
        task = await session.whoami(Request(name="whoami"))
        result = await client.wait_task_finish(task)
        print(f"Whoami: {result.spite.response.output}")

asyncio.run(main())
```

> **运行示例**: `cd examples && python whoami.py`

## 三大核心功能

### 1. 服务器连接

```python
from IoM import MaliceClient

# 方式一：使用认证文件（推荐）
client = MaliceClient.from_config_file("client.auth")

# 方式二：手动配置
from IoM import ClientConfig
config = ClientConfig(
    host="127.0.0.1", port=5004, operator="admin",
    ca_certificate="...", certificate="...", private_key="..."
)
client = MaliceClient(config)

# 连接并获取服务器信息
async with client:
    from IoM.proto.clientpb import Empty
    basic = await client.get_basic(Empty())
    print(f"服务器版本: {basic.version}")
```

### 2. 会话管理

```python
# 发现并管理所有会话
await client.update_sessions()
sessions = client.cached_sessions
print(f"发现 {len(sessions)} 个会话")

# 获取会话详情
for session_id, info in sessions.items():
    print(f"会话: {info.name} ({session_id[:8]}...)")
    print(f"存活: {info.is_alive}")

# 获取会话操作器
session = await client.sessions.get_session(session_id)
```

### 3. 命令执行

```python
from IoM.proto.modulepb import Request

# 系统信息命令
task = await session.whoami(Request(name="whoami"))
task = await session.pwd(Request(name="pwd"))
task = await session.ps(Request(name="ps"))

# 文件系统操作
task = await session.ls(Request(name="ls"))
task = await session.cd(Request(name="cd", input="/tmp"))

# 等待任务完成并获取结果
result = await client.wait_task_finish(task)
if result.spite and result.spite.response:
    print(f"输出: {result.spite.response.output}")
```

## 动态 API

SDK 自动转发所有 133 个 gRPC 方法，无需手动实现：

```python
from IoM.proto.clientpb import Empty, SessionRequest

# 服务器操作（133个方法全部可用）
basic = await client.get_basic(Empty())
sessions = await client.get_sessions(SessionRequest(all=True))
listeners = await client.get_listeners(Empty())

# 会话操作（自动注入 session_id）
from IoM.proto.modulepb import ExecRequest
task = await session.execute(ExecRequest(
    path="/bin/bash",
    args=["-c", "ls -la"]
))
```

## 示例代码

```bash
# 查看完整示例
cd examples/
python whoami.py    # 基础命令执行
```

## 错误处理

```python
from IoM.exceptions import MaliceError, ConnectionError

try:
    async with client:
        result = await session.whoami(Request(name="whoami"))
except ConnectionError:
    print("服务器连接失败")
except MaliceError as e:
    print(f"执行错误: {e}")
```

## 认证文件格式

服务器生成的 `client.auth` 文件：

```yaml
operator: admin
host: 127.0.0.1
port: 5004
ca: |
  -----BEGIN CERTIFICATE-----
  ...
  -----END CERTIFICATE-----
cert: |
  -----BEGIN CERTIFICATE-----
  ...
  -----END CERTIFICATE-----
key: |
  -----BEGIN PRIVATE KEY-----
  ...
  -----END PRIVATE KEY-----
```

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 重新生成协议文件
python generate.py

# 运行测试
pytest
```

## 特性总结

- **动态 API**: 自动转发 133 个 gRPC 方法
- **类型安全**: 完整的 .pyi 类型提示
- **会话管理**: 自动会话上下文注入
- **异步支持**: 现代 async/await 模式
- **mTLS 安全**: 双向 TLS 认证
- **错误处理**: 完善的异常处理机制

## 相关链接

- [文档](https://chainreactors.github.io/wiki/IoM/)
- [GitHub](https://github.com/chainreactors/malice-network)
- [Issues](https://github.com/chainreactors/malice-network/issues)

---

**Requirements**: Python 3.10+, 详见 `pyproject.toml`

**License**: MIT License