# MinerU CLI 使用指南

> 来源: MinerU 官方 CLI 工具文档整理
> 适用: LearnAnything 项目 PDF 解析增强
> 更新日期: 2026-07-10

---

## 1. 工具简介

MinerU 提供 **云端 CLI 工具** `mineru-open-api`，零依赖、免 GPU、免模型下载，直接通过命令行调用 MinerU 云端服务解析 PDF 等文档。

- **安装方式**（Windows PowerShell）:
  ```powershell
  irm https://cdn-mineru.openxlab.org.cn/open-api-cli/install.ps1 | iex
  ```
- **验证安装**:
  ```powershell
  mineru-open-api version
  ```

---

## 2. 两种核心模式

### 2.1 Flash 模式（免 Token）

- **特点**: 无需配置 Token，拿来即用
- **限制**: 单文件 ≤ 10MB，≤ 20 页
- **输出**: 仅 Markdown
- **适用**: 快速预览、轻量测试、AI Agent 轻量调用

```powershell
# 解析本地 PDF，输出到终端
mineru-open-api flash-extract report.pdf

# 解析网络 PDF
mineru-open-api flash-extract https://example.com/paper.pdf

# 指定保存目录、语言、页码范围
mineru-open-api flash-extract report.pdf -o ./output/ --language en --pages 1-10
```

### 2.2 Extract 模式（需 Token）

- **特点**: 功能更强，支持批量，输出格式更多
- **限制**: 单文件 ≤ 200MB，≤ 600 页
- **输出**: Markdown + HTML + LaTeX + DOCX + JSON
- **适用**: 正式项目、大文件解析、数据存档

**Token 配置方式**（三选一）:

1. **命令行传参**（每次调用）:
   ```powershell
   mineru-open-api extract report.pdf --token <your-token>
   ```

2. **环境变量**（推荐，一劳永逸）:
   ```powershell
   $env:MINERU_TOKEN = "<your-token>"
   mineru-open-api extract report.pdf
   ```

3. **配置文件交互**:
   ```powershell
   mineru-open-api auth
   # 按提示输入 Token，保存到本地配置文件
   ```

**常用命令**:

```powershell
# 单文件解析（默认输出 Markdown）
mineru-open-api extract report.pdf

# 指定输出目录和格式
mineru-open-api extract report.pdf -o ./results/ -f md

# 扫描件强制开启 OCR
mineru-open-api extract scanned-paper.pdf --ocr

# 关闭公式识别（加快处理）
mineru-open-api extract report.pdf --formula=false

# 批量解析目录下所有 PDF
mineru-open-api extract .\*.pdf -f md -o ./markdown-archive/

# 基于文件列表批量处理
mineru-open-api extract --list files.txt -o ./results/

# 管道传给其他工具
mineru-open-api extract report.pdf | some-llm-tool "总结核心观点"
```

---

## 3. 输出格式说明

| 参数 | 输出格式 | 说明 |
|------|---------|------|
| `-f md` (默认) | Markdown | 结构化文本，含标题、列表、图片引用、公式、表格 |
| `-f html` | HTML | 富文本格式，适合浏览器查看 |
| `-f docx` | Word 文档 | 可直接编辑的 Office 文档 |
| `-f latex` | LaTeX | 学术排版格式 |
| `-f json` | JSON | 结构化数据，含布局信息、边界框等 |

**Markdown 输出特点**:
- 标题层级: `#` `##` `###` 自动识别
- 图片: `![image](URL)` 云端托管链接
- 公式: `$$LaTeX$$` 块级公式，或 `$LaTeX$` 行内公式
- 表格: `\| 列1 \| 列2 \|` 标准 Markdown 表格
- 列表: `-` 无序列表，`1.` 有序列表

---

## 4. Python SDK 用法（项目集成参考）

```python
# 安装: pip install mineru-open-sdk
from mineru import MinerU

# Flash 模式（免 Token）
client = MinerU()
result = client.flash_extract("扫描件.pdf")
print(result.markdown)

# Extract 模式（需 Token）
client = MinerU("your-api-token")
result = client.extract("report.pdf")
result.save_markdown("./output/report.md")
result.save_all("./output/report/")  # 保存所有格式

# 批量处理
for result in client.extract_batch(["a.pdf", "b.pdf", "c.pdf"]):
    result.save_all(f"./output/{result.filename}/")
    print(f"{result.filename}: 完成")
```

---

## 5. 与 LearnAnything 项目集成思路

```
DocumentProcessor._process_pdf()
    │
    ├─ 默认模式: PyMuPDF（快速、轻量、无网络依赖）
    │
    └─ 高级模式: MinerU CLI（结构化 Markdown，含图片/公式/表格）
           │
           ├─ 调用: mineru-open-api extract <pdf> -o <tmp_dir> -f md
           │
           ├─ 读取: <tmp_dir>/content.md
           │
           ├─ 解析 Markdown 结构
           │   ├─ 标题层级 → 章节 chunk
           │   ├─ 图片引用 → image chunk（含 URL/路径）
           │   ├─ 公式块 → formula chunk（含 LaTeX）
           │   └─ 表格 → table chunk（含 Markdown 表格）
           │
           └─ 生成标准 chunk 列表，接入后续流程
```

---

## 6. 常见问题

| 问题 | 解决 |
|------|------|
| Token 失效 | 到 https://mineru.net/apiManage/token 重新申请 |
| 文件太大 | 超过 200MB 需拆分 PDF，或用 Flash 模式（10MB） |
| 图片下载 | Markdown 中的图片 URL 是云端托管，可下载到本地 |
| 网络限制 | 确保能访问 mineru.net 和 cdn-mineru.openxlab.org.cn |

---

## 7. 参考链接

- MinerU 生态主页: https://mineru.net/ecosystem
- Python SDK GitHub: https://github.com/opendatalab/mineru-open-sdk
- CLI GitHub: https://github.com/opendatalab/mineru-open-api-cli
- Token 申请: https://mineru.net/apiManage/token
- API 文档: https://mineru.net/apiManage/docs
