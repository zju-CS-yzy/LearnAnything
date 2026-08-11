# LearnAnything 部署指南 (LA-DEPLOY-FEAT)

## 📦 部署方式：压缩包（推荐）

### 用户操作步骤

1. **下载压缩包**
   - 从 Release 页面下载 `LearnAnything-vX.X.X.zip`

2. **解压到任意目录**
   ```
   LearnAnything-v1.0.0/
   └── LearnAnything/
       ├── LearnAnything.exe      ← 启动程序
       ├── _internal/             ← Python 运行时 + 依赖
       ├── web/                   ← 前端文件
       ├── config/                ← 配置文件目录
       ├── knowledge_base/        ← 知识库目录
       └── tools/                 ← 工具目录
           └── mineru/
               └── mineru-open-api.exe  ← MinerU CLI（PDF解析工具）
   ```

3. **运行程序**
   - 双击 `LearnAnything.exe`
   - 程序将启动由 PyInstaller 打包的 PyQt5 桌面图形界面；前端页面显示在程序内置的 `QWebEngineView` 中，不会自动打开外部浏览器
   - 桌面程序会在后台启动仅供自身使用的本地 FastAPI 服务，并将其加载到内置界面；用户无需手动访问任何 localhost 地址

4. **首次启动配置**
   - 在全新设备或尚无系统管理员的数据目录中，先注册或登录一个密码账户，并按提示重新输入密码，一次性认领首位本机管理员
   - 管理员认领成功后会弹出配置向导
   - **按功能模块配置 API**，而非按模型配置：
     - 💬 **语言处理**（LLM）— 智能对话、语义提取、评测
     - 👁️ **视觉处理**（VLM）— 图片描述、表格提取、公式识别  
     - 📊 **文本向量化**（Embedding）— 语义搜索
     - 📄 **PDF 解析**（MinerU）— PDF 结构化提取
   - **MinerU 配置说明**：
     - MinerU CLI 已包含在压缩包中（`tools/mineru/mineru-open-api.exe`），无需额外安装
     - 但需要到 [mineru.net](https://mineru.net/apiManage/token) 申请免费 Token
     - 在配置向导中粘贴 Token 即可使用
   - 每个功能可独立选择服务商和模型
   - 点击"测试"验证 API 连通性
   - 点击"完成配置"保存

### 推荐配置方案

| 方案 | 语言处理 | 视觉处理 | 文本向量化 | 特点 |
|:---|:---|:---|:---|:---|
| **A（推荐）** | DeepSeek | 智谱AI | 智谱AI | 性价比高，国内稳定 |
| **B（一站式）** | OpenAI GPT-4o | OpenAI GPT-4o | OpenAI | 功能最全，国际领先 |
| **C（国内便捷）** | 硅基流动 | 硅基流动 | 硅基流动 | 国内一站式平台 |

> 💡 **语言处理** 和 **文本向量化** 是**必须**的，没有配置会导致核心功能不可用。
> 
> 👁️ **视觉处理** 和 📄 **PDF 解析** 是可选的，不配置时对应功能将降级或禁用。

---

## 系统管理员初始化（AUTH-P0-2）

配置读取、修改、连接测试和系统级 LLM 运维接口只允许密码账户中的系统管理员访问。系统不会把首个注册用户自动提升为管理员，也不允许无密码的 `default/anonymous` 用户成为管理员。

当系统尚无管理员时，本机密码账户登录后会看到“初始化本机管理员”。重新输入当前密码即可完成一次性认领。该入口只接受回环地址请求，认领过程使用数据库原子事务，并在首位管理员产生后永久关闭。

首位管理员可以在侧边栏“用户管理”页面授予或撤销其他管理员；每次角色变更都必须重新输入当前管理员密码，且系统禁止撤销最后一个管理员。

CLI 保留为前端不可用或管理员账户无法恢复时的应急工具：

```bash
python scripts/manage_admin.py list
python scripts/manage_admin.py promote <username>
python scripts/manage_admin.py demote <username>
```

工具同样会阻止撤销或删除最后一个系统管理员。生产环境不应直接修改 `users.db`，也不应通过远程注册接口自动分配管理员角色。本机自助认领不适用于远程服务器部署；服务器模式后续应使用一次性初始化码。

---

## 🔧 开发者构建

### 前置要求

- Python 3.10+
- Node.js 18+
- PyInstaller

### 构建步骤

```bash
# 1. 安装 Python 依赖
pip install -r requirements.txt

# 2. 使用构建脚本（自动处理前端依赖安装）
python scripts/build-release.py v1.0.0

# 3. 输出在 dist/LearnAnything-v1.0.0-YYYYMMDD.zip
```

> 💡 **构建脚本会自动检测前端依赖**：如果 `web-vue/node_modules` 不存在，会自动运行 `npm install` 安装。Release 仓库无需手动维护 `node_modules`。>

---

## 🛠️ 技术架构

### 功能模块配置系统 (LA-DEPLOY-FEAT)

区别于传统的"按模型配置"，LearnAnything 采用"**按功能配置**"的架构：

```
功能层 ────────→ 配置层 ────────→ 实现层
语言处理(LLM)     api_config.ini    DeepSeek / OpenAI / 硅基流动
视觉处理(VLM)     api_config.ini    智谱AI / OpenAI / 硅基流动
文本向量化(EMB)   api_config.ini    智谱AI / OpenAI / 硅基流动
PDF解析(MinerU)   api_config.ini    MinerU CLI
```

**优势**：
- 用户可根据 API 可用性自由组合
- 新增提供商只需在配置层注册，无需修改业务代码
- 单个功能模块故障不影响其他功能

### 配置文件格式

`config/api_config.ini`（首次配置后自动生成）：

```ini
[llm]
provider = deepseek
api_key = sk-xxxxxxxx
base_url = https://api.deepseek.com/v1
model = deepseek-chat
enabled = True

[vlm]
provider = zhipu
api_key = xxxxxxxx.xxxxxxxxxxxxxxxx
base_url = https://open.bigmodel.cn/api/paas/v4
model = glm-4.5v
enabled = True

[embedding]
provider = zhipu
api_key = xxxxxxxx.xxxxxxxxxxxxxxxx
base_url = https://open.bigmodel.cn/api/paas/v4
model = embedding-3
enabled = True

[mineru]
provider = mineru
api_key = xxxxxxxx
enabled = True
```

### 路径处理

所有代码使用**相对路径**或**运行时推断路径**，支持任意部署位置：

```python
# config/settings.py — 项目根目录自动推断
PROJECT_ROOT = Path(__file__).parent.parent

# app.spec — PyInstaller 内置 SPECPATH
project_root = Path(SPECPATH)

# 数据目录 — 相对于项目根目录
KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "knowledge_base"
```

### 向后兼容

- 旧格式 `config/api_keys.ini` 会在首次加载时**自动迁移**到新格式
- 环境变量（DEEPSEEK_API_KEY, ZHIPU_API_KEY 等）仍然有效，优先级低于配置文件

---

## 📋 变更记录

| 文件 | 变更 |
|:---|:---|
| `config/settings.py` | 重构为功能模块配置系统，支持多提供商 |
| `app/setup_api.py` | 重写为功能模块配置 API，增加提供商列表、测试接口 |
| `web-vue/src/components/SetupWizard.vue` | 重写为功能模块配置向导，增加推荐方案、提供商选择 |
| `core/llm_client.py` | 从功能配置读取，解耦 DeepSeek 硬编码 |
| `core/vlm_client.py` | 从功能配置读取，支持任意多模态 API |
| `core/embedding.py` | 从功能配置读取，支持任意 Embedding API |
| `core/mineru_client.py` | 从功能配置读取 Token |
| `core/dialog_context.py` | 修复硬编码路径 |
| `core/graph_store.py` | 修复硬编码路径 |
| `agents/message_bus.py` | 修复硬编码路径 |
| `app.spec` | 修复硬编码项目路径 |
| `app/backend_api.py` | 注册 setup_api 路由 |
| `web-vue/src/App.vue` | 集成 SetupWizard |
| `scripts/build-release.py` | 新增一键构建脚本 |
