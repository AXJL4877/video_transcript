# MODULE_SPEC.md

本文档定义处理模块 `module.json` 必须遵守的规范。任何新增模块（或 AI 助手）都必须严格按本规范编写，否则前端 DynamicForm / 结果展示与后端处理会对不上。

本地 HTTP 微服务（如 `text_to_voice`）在遵守本规范核心字段的同时，使用 **`local` 扩展** 声明端口与代理（见 §8）。宿主扫描 `module.json` 自动注册，禁止再改硬编码表。

---

## 1. 目录结构约定

每个模块必须是一个独立文件夹。

**理想形态（任务型前后端分离）**
```
frontend/modules/<module-id>/
├── module.json     # 必须（可与后端一致，或为子集）
├── index.ts        # 可选：仅当需要自定义 UI 时导出 { Form?, Result? }
├── Form.tsx        # 可选，缺省 DynamicForm（§9）
├── Result.tsx      # 可选，缺省按 output_schema 渲染（§9）
└── hooks.ts        # 可选

backend/modules/<module-id>/
├── module.json     # 必须，与前端一致（或前端为子集）
└── handler.py      # 必须，实现统一 run()
```

**当前仓库形态（本机独立 HTTP 服务）**
```
mo_kuai/<folder>/
├── module.json     # 必须（含 §2 核心字段 + §8 local）
├── AGENTS.md
├── web/            # 必须：独立检验 UI（挂到 /ui）
├── start_web.*     # 必须：一键启动并打开 /ui
└── …服务代码与启动脚本
```

> 任务型模块：`<module-id>` 与 `id` 均为 kebab-case 且一致。  
> 已上线本地服务：`id` 已固定为 `tts` / `compose` / `download` / `richtext` / `ai-in`（不可为兼容性而改名；展示用 `name`）。

---

## 1.1 独立检验（强制）

**每个模块必须能在不接入宿主（不启动 video_1 / 壳）的情况下，被人工独立验收。**

最低要求（本机 HTTP 模块）：

| 项 | 要求 |
|---|---|
| `GET /health` | 已有；`service` === `local.label` |
| `GET /ui`（或 `/ui/`） | 浏览器可操作的调试页，能覆盖本模块主能力（对应 `local.endpoint` / 主业务流程） |
| `start_web.bat`（及对应 `.ps1`） | 启动服务（若未运行）并打开 `/ui`；用户双击即可验收 |

禁止只靠「让宿主调 API」才能验证。单元测试 / curl 脚本可作为补充，**不能替代** `/ui` + `start_web`。

任务型模块：至少提供可本地跑通的最小验收路径（示例输入 + 预期输出，或本地 smoke 命令），写进该模块 `AGENTS.md`。

---

## 1.2 模块间单独（解耦与自足）（强制）

**每个模块必须自足：只启动它自己就能用起来，不得要求用户先手动去启动别的模块。**

- **默认无横向依赖**：一个模块不应依赖另一个模块「已经在跑」。缺依赖时**禁止**直接抛
  「请先启动 X 模块」让用户自己去开——这类硬依赖是接入事故的常见来源。
- **编排型模块是唯一例外，但必须自愈**：像 `video_transcript` 这种「组合别人」的模块，
  其**启动脚本必须在启动时自动探测并拉起下游**（扫描同级 / `Desktop` / `Desktop/mo_kuai`
  下的模块文件夹，调用其 `start*.bat`），拉起失败才降级为清晰提示 + 手动指引。
  用户体验上必须是「只启动编排模块一个即可」。
- **发现靠注册表 + health，不靠假设**：下游地址一律走 `环境变量 → ports.json → 默认端口探活`，
  并用 `/health.service === label` 校验命中，**禁止**写死 `127.0.0.1:固定端口`。
- **依赖状态要可见**：编排型模块的 `/health` 需带 `downstream`（各下游 `{ok, baseUrl}`），
  `/ui` 状态栏应能显示下游是否在线。
- **解耦即独立**：这条与 §1.1 一致——「独立」= 不依赖宿主壳、也不依赖别的模块被手动拉起；
  代码上可复用别的服务，但**运行上必须自足**。

---

## 2. module.json 完整字段规范

```json
{
  "id": "video-upscale",
  "name": "视频超分辨率",
  "description": "将输入视频提升到指定分辨率",
  "version": "1.0.0",
  "category": "video",

  "input_schema": {
    "video_file": {
      "type": "file",
      "accept": ["video/mp4", "video/mov"],
      "required": true,
      "label": "原始视频"
    },
    "scale": {
      "type": "enum",
      "options": [2, 4],
      "default": 2,
      "required": true,
      "label": "放大倍数"
    }
  },

  "output_schema": {
    "result_video": {
      "type": "file",
      "mime": "video/mp4"
    },
    "log": {
      "type": "string"
    }
  },

  "ui_hint": {
    "form_layout": "vertical",
    "icon": "video",
    "estimated_time_seconds": 60
  },

  "runtime": {
    "async": true,
    "queue": "gpu-queue",
    "timeout_seconds": 600
  }
}
```

### 字段说明

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | ✅ | 全局唯一；任务型用 kebab-case 且与文件夹名一致；一旦发布不可更改 |
| `name` | ✅ | 前端展示名 |
| `description` | ✅ | 模块简介 |
| `version` | ✅ | 模块版本，如 `1.0.0` |
| `category` | ✅ | `video` / `image` / `text` / `system` 等 |
| `input_schema` | ✅ | 输入参数，见 §3 |
| `output_schema` | ✅ | 输出结果，结构同 §3 |
| `ui_hint` | ❌ | 渲染提示；本地服务可用 `service_panel` / `hidden` |
| `runtime` | ✅ | 调度信息；AI 类建议 `timeout_seconds` ≥ 120 |
| `local` | △ | 本机 HTTP 服务必填，见 §8 |
| `capabilities` | ✅ | **能力登记清单**（含主 endpoint 之外的所有小功能），接入完成定义，见 §10 |

---

## 3. input_schema / output_schema 字段类型

每个参数为 key → 描述对象：

| type | 说明 | 额外属性 |
|---|---|---|
| `string` | 文本 | `max_length`, `default`, **`format`**（见下） |
| `number` | 数字 | `min`, `max`, `default` |
| `enum` | 下拉 | `options`, `default` |
| `boolean` | 开关 | `default` |
| `file` | 单文件 | `accept`（MIME 数组）, `max_size_mb`, `mime`（输出） |
| `file[]` | 多文件 | 同上 |

通用属性：`required`、`label`、`description`。

### `format`（string 专用）

| format | 渲染 |
|---|---|
| （缺省） | 单行 `<input>` |
| `textarea` | 多行 `<textarea>`（系统提示词 / 正文 / 长 prompt **优先用这个**，不要为此单独写 Form.tsx） |

示例：

```json
"prompt": {
  "type": "string",
  "format": "textarea",
  "required": true,
  "label": "提示词",
  "description": "描述希望生成的内容",
  "default": ""
}
```

> DynamicForm 按此表渲染。新增 type / format 必须同步更新 DynamicForm、`FieldSpec` 与本文档。

### 默认值同源（强制）

- 表单默认值**只**来自 `input_schema.*.default`
- 禁止在 `Form.tsx` 里另维护一套 `DEFAULTS` 硬编码（长期与 schema 漂移）
- 自定义 Form 若存在，初始化时必须 `defaultsFromSchema(manifest.input_schema)`

---

## 4. 后端 handler.py（任务型模块）

```python
from modules._base import BaseModuleHandler

class Handler(BaseModuleHandler):
    def run(self, params: dict) -> dict:
        # params 符合 input_schema；文件字段为本地路径字符串
        # return 符合 output_schema；文件输出为 storage.upload() 后的 URL
        ...
```

约定：

- **只暴露** `run(params) -> dict`；返回 key 必须对齐 `output_schema`
- 密钥走环境变量 / 共享配置，**禁止**写进模块源码或提交 `.env`
- 超时写进 `runtime.timeout_seconds`（AI 类建议 ≥ 120）
- 同目录依赖：壳可能按单文件加载 handler；**避免**脆弱的相对导入（`from .foo import`）。优先同目录 `importlib` 加载，或把共享代码放到可导入包路径
- 启动时 `module_loader` 扫描并校验 `module.json` + `handler.py`，失败则拒绝启动

---

## 5. 任务数据流（任务型）

1. `GET /api/modules` → 所有 module.json  
2. `POST /api/tasks { module_id, input_params }` → `{ task_id, status: "pending" }`  
3. Worker：`get_handler(module_id).run(input_params)`  
4. `GET /api/tasks/{task_id}` → status / result / error  
5. 前端：有自定义 `Result` 则用之，否则按 `output_schema` 默认渲染  

**本机服务流（mo_kuai HTTP）**

1. `GET /studio-api/launcher/modules` → 扫描到的 module.json  
2. 前端/代理按 `local.proxy` 转发到独立进程  
3. 按 `local.endpoint` 调用 HTTP；`runtime.async=true` 时轮询任务接口  

---

## 6. 命名与版本

- `id` 上线后永久不可改；展示改名只用 `name`
- breaking change → 新 `id`（如 `tts-v2`），不要改旧 schema
- `version` 暂仅记录，不做自动兼容校验

---

## 7. 新增模块 Checklist

**任务型（KE 壳）**
- [ ] `backend/modules/<id>/module.json` + `handler.py`（§4）
- [ ] `frontend/modules/<id>/module.json`（一致）
- [ ] **`capabilities[]` 登记所有能力**（含主 endpoint 之外的小功能，§10）
- [ ] **默认 DynamicForm**；仅必要时才加 `Form.tsx` / `Result.tsx` + `index.ts`（§9）
- [ ] 长文本字段用 `format: "textarea"`，不要为此手写 Form
- [ ] 默认值只写在 schema；自定义 Form 不另写 DEFAULTS
- [ ] **不**改 worker if-else、导航硬编码表、`tasks.py` 里的 module_id 分支

**本机 HTTP（mo_kuai）**
- [ ] 文件夹 + 符合 §2 的 `module.json`（含 §8 `local` + §10 `capabilities`）
- [ ] 实现 `/health`（`service` === `local.label`）+ 业务 API
- [ ] **独立检验**：`GET /ui` + `start_web.*`（§1.1）；不接宿主也能验收主能力
- [ ] **`capabilities[]` 登记所有能力**，并附**自检脚本**（§10）；`verify` 全绿才算接入完成
- [ ] 放到 Desktop 或 `Desktop/mo_kuai/` 扫描根
- [ ] 重启 studio-api / Vite；确认 `/launcher/modules` 可见
- [ ] **不**改 launcher / vite-local-proxy / LocalServiceId 硬编码表

**接入他人模块时（防「小功能被漏接」）**
- [ ] 打开该模块 `module.json` → `capabilities[]`，**逐条**核对
- [ ] `must_keep: true` 的能力一律不得丢失 / 被宿主屏蔽（如 cookie 自动拉取、风控头）
- [ ] 跑模块自检：直连一遍 + `--base <宿主> --prefix <代理前缀>` 过代理再跑一遍，全绿
- [ ] `manual` 能力项按脚本提示人工确认

---

## 8. `local` 扩展（本机 HTTP 服务）

```json
"local": {
  "label": "text_to_voice",
  "defaultPort": 8765,
  "maxTries": 15,
  "envPort": "TTS_PORT",
  "healthPath": "/health",
  "endpoint": { "method": "POST", "path": "/tts" },
  "start": {
    "windows": { "script": "start_api.ps1", "runtime": "powershell" }
  },
  "proxy": [
    {
      "prefix": "/tts-api",
      "rewrite": { "pattern": "^/tts-api", "replacement": "" }
    }
  ]
}
```

| 字段 | 说明 |
|------|------|
| `label` | `/health.service` 必须等于此值 |
| `defaultPort` / `maxTries` / `envPort` | 端口协商 → ports.json |
| `start` | launcher 一键启动 |
| `proxy` | Vite 代理；`pathEquals` 精确匹配 |
| `endpoint` | 主操作 HTTP 路径（对应 input/output_schema） |

`ui_hint.service_panel: false` 或 `ui_hint.hidden: true` → 不出现在设置「本地后端」列表。

扫描实现：`video_1/shared/discoverModules.mjs`  
列表 API：`GET /studio-api/launcher/modules`

### 现有模块

| 目录 | id | category | defaultPort |
|------|-----|----------|-------------|
| text_to_voice | tts | text | 8765 |
| video_creat | compose | video | 8787 |
| video_download | download | video | 8789 |
| audio_asr | asr | text | 8791 |
| rich_txt | richtext | text | 8793 |
| video_remotion | remotion | video | 8797 |
| video_transcript | transcript | text | 8799 |
| AI_in | ai-in | text | 8795 |

> `defaultPort` **全局唯一**：新增模块前先查本表挑一个没被占用的默认端口，不要撞车
> （历史上 `rich_txt` 与 `asr` 都用过 8791，已把 `rich_txt` 挪到 8793）。

### 8.1 端口智能顺延（强制）

`defaultPort` 只是**首选**，不是硬绑定。每个模块启动/被发现时必须遵守：

1. **顺延占用**：首选端口被占 → 在 `defaultPort … defaultPort+maxTries-1` 范围内自动找下一个空闲端口启动
   （参考 `claimServicePort` / `Find-LiveServiceInstance` / `Resolve-*Port`）。
2. **写回真实端口**：启动后把**实际端口**写进 `%USERPROFILE%\.scene-studio\ports.json`（含 `baseUrl`），
   供宿主 / 编排模块发现。**禁止**假设别人跑在 `defaultPort`。
3. **按 service 名认领，不是按端口**：探活命中要校验 `/health.service === local.label` 才算数；
   端口上是别的服务（名字不符）→ 跳过继续顺延。这样即使两个模块默认端口撞车也能各自自愈。
4. **复用已存在实例**：发现同名健康实例 → 刷新 ports.json 后**复用并退出**，不要再起第二个。
5. **envPort 覆盖**：允许用 `local.envPort`（如 `PORT` / `ASR_PORT`）固定端口（LAN/调试用）；
   指定端口被占时仍按第 1 条顺延并告警。
6. **调用方零硬编码**：前端 / launcher / 编排模块一律从 ports.json 取 `baseUrl`，
   `module.json.local.proxy` 也只认前缀、不写死端口。

> 一句话：**默认端口可撞、但运行必自愈**——顺延 + 按名认领 + 写回注册表，三者缺一不可。

---

## 9. 前端 UI 约定（任务型 / KE 壳）

### 9.1 默认优先 DynamicForm

- **默认**只用 `module.json` + DynamicForm，不要为「好看」手写表单
- 仅当 DynamicForm 撑不住时才写 `Form.tsx` / `Result.tsx`：多步交互、富文本编辑器、复杂预览等
- 简单字段（string / number / enum / boolean / file）禁止自定义 Form
- 长 prompt / 正文 → `format: "textarea"`，仍走 DynamicForm

### 9.2 自定义 UI 注册（禁止手写 module_id 表）

```
frontend/modules/<id>/index.ts  →  export { Form?, Result? }
```

- 壳通过 `import(\`./${id}/index\`)` **自动发现**；有则用之，无则 DynamicForm / 默认 Result
- **禁止**在 `tasks.py`、导航、worker if-else、手动 `_ui-registry` 大表里写死 `module_id`
- 无自定义 UI 的模块**不要**建空的 `index.ts`

### 9.3 视觉 token（自定义 Form 必须遵守）

全模块共用壳的设计 token，**禁止**模块内再引入第二套颜色 / 圆角 / 阴影：

| 用途 | class |
|------|--------|
| 容器（短表单） | `max-w-lg space-y-4` |
| 容器（长文案 / textarea） | `max-w-3xl space-y-4` |
| 控件 | `border-input bg-background rounded-md text-sm`（及壳统一的 h/px） |
| 说明文案 | `text-xs text-muted-foreground`，放在 **label 下方** |
| 主提交 | 一个主按钮 |
| 次要操作 | `variant="outline"` + `size="sm"` |

### 9.4 字段布局

| 类型 | 布局 |
|------|------|
| 主题 / 提示词 / 正文等长文本 | **一栏**（`format: "textarea"`） |
| model、temperature、max_tokens 等参数条 | **两栏** `grid grid-cols-2 gap-3`（自定义 Form 时） |
| 文件 | 一栏 |

### 9.5 Result 区

- 成功态：标题 + 次要 meta（模型、字数等）**一行**，下面才是主内容
- 富文本 / 视频 / 文件：一种主预览即可，**不要**堆原始 JSON
- 操作：复制 / 下载用一排 `outline` + `sm`，文案短（如「复制 HTML」）

### 9.6 第三方编辑器依赖

若模块依赖 wangEditor 等：安装后需**重启前端**；补齐 CSS module 类型声明（如 `*.css`），避免 TS 报错阻塞接入。

### 9.7 职责边界：外壳提供什么 / 模块只负责什么

任务卡片的「外框」由外壳统一提供，**所有模块自动继承，禁止在模块内重造**。模块只负责表单输入与结果内容本身。

**外壳已提供（模块不要碰）**

| 能力 | 实现位置 | 说明 |
|------|----------|------|
| 任务卡片容器 / 标题 / 时间 | `components/task-queue-list/TaskCard.tsx` | 你的 `Result` 渲染在其 `CardContent` **内部** |
| 删除按钮（含二次确认 + 退场动画） | `TaskCard.tsx` → `DELETE /api/tasks/{id}` | 模块**不要**自建删除按钮或删除接口 |
| 任务列表：计数、清空已完成、折叠已完成/失败、进出场动画 | `TaskQueueList.tsx` → `DELETE /api/tasks` | 通用逻辑，与 `module_id` 无关 |
| 进度条：状态配色 / 中文标签 / 处理中动画 | `components/progress-tracker/ProgressTracker.tsx` | 由任务 `status` 驱动，模块无需传进度 |
| 错误信息展示 | `TaskCard.tsx` | 读 `task.error_message`，模块只需在 `handler` 抛错 |
| 轮询刷新（5s） | `TaskQueueList.tsx` | 模块不用管刷新 |
| 设计 token（颜色 / 圆角 / 阴影 / 间距） | `app/globals.css` + `tailwind.config.ts` | 见 §9.3，模块只能复用 |
| 基础组件 | `components/ui/{button,card,progress,dialog,form}.tsx` | 自定义 UI 只能用这些，不得引第二套组件库 |

**模块只负责**

| 职责 | 缺省行为 | 自定义入口 |
|------|----------|-----------|
| 表单输入 | `DynamicForm`（按 `input_schema` 渲染） | `modules/<id>/index.ts` 导出 `Form`（§9.1 撑不住时才写） |
| 结果内容 | `DefaultResult`（按 `output_schema` 渲染） | 同上导出 `Result`（见 §9.8） |
| 后端处理 | — | `backend/modules/<id>/handler.py` 的 `run()`（§4） |

> 一句话：**外壳负责「任务怎么被管理和展示」，模块只负责「输入长什么样、结果长什么样、后台怎么算」。**
> 凡是删除 / 进度 / 列表 / 动画 / 刷新，都不是模块该写的东西。

### 9.8 自定义 Result 的正确示例

仅当 `DefaultResult` 撑不住（需要专属预览 / 多产物排版）时才写。约束：

- **不要**再包一层 `Card`——外壳的 `TaskCard` 已经是卡片，你渲染在它内部。
- **只用** `components/ui/*` 与设计 token（§9.3），禁止自带配色 / 圆角 / 阴影。
- 结构遵守 §9.5：标题 + 次要 meta **一行**，下面一种主预览，操作用一排 `outline` + `sm`。
- **不要**堆原始 JSON，**不要**自建删除 / 进度 / 时间（外壳已给）。
- Props 固定为 `{ result, manifest }`（见 `_ui-registry.ts` 的 `ModuleResultProps`）。

`frontend/modules/<id>/Result.tsx`：

```tsx
"use client";

import { Button } from "@/components/ui/button";
import type { ModuleResultProps } from "@/modules/_ui-registry";
import { useState } from "react";

export function Result({ result, manifest }: ModuleResultProps) {
  const [copied, setCopied] = useState(false);

  // result 的 key 对齐 module.json 的 output_schema
  const html = String(result.html ?? "");
  const wordCount = result.word_count as number | undefined;

  async function copyHtml() {
    await navigator.clipboard.writeText(html);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="max-w-3xl space-y-3">
      {/* 标题 + 次要 meta 一行（§9.5） */}
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="text-base font-medium">{manifest.name} 结果</h3>
        {wordCount != null && (
          <span className="text-xs text-muted-foreground">{wordCount} 字</span>
        )}
      </div>

      {/* 一种主预览，复用 token，不堆 JSON */}
      <div
        className="max-h-[420px] overflow-auto rounded-md border border-input bg-background p-3 text-sm"
        dangerouslySetInnerHTML={{ __html: html }}
      />

      {/* 操作：一排 outline + sm，文案短 */}
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" onClick={copyHtml}>
          {copied ? "已复制" : "复制 HTML"}
        </Button>
      </div>
    </div>
  );
}
```

`frontend/modules/<id>/index.ts`（自动发现，§9.2）：

```ts
export { Result } from "./Result";
// 若还需自定义表单：export { Form } from "./Form";
```

> 文件产物（视频 / 图片 / 下载）可直接参考并复用 `components/dynamic-form/DefaultResult.tsx` 的主预览分支，通常**无需**自定义 Result。

---

## 10. 能力登记与接入自检（强制）

> 解决的问题：核心能力没问题，但 **cookie 自动拉取这类「小功能」在接入时经常被漏接**。
> 根因是这些小动作只散落在代码/散文里，没有一份「必须逐条验收」的结构化清单。
> 本节把每个能力登记成机器可读、可自动探测的条目，作为**接入完成定义(DoD)**。

### 10.1 `capabilities[]` 字段

`module.json` 顶层新增数组 `capabilities`，把**所有**能力（含主 endpoint 之外的辅助动作：
自动拉取、风控绕过、落盘清理、重试、并发限制、代理透传等）逐条登记。

```json
"capabilities": [
  {
    "id": "cookie-one-click-import",
    "desc": "一键 cookie 导入（浏览器+CDP 落盘），宿主需代理 /cookies/* 并在 UI 暴露入口",
    "kind": "aux",
    "must_keep": true,
    "endpoints": ["GET /cookies/sites", "POST /cookies/login", "POST /cookies/save"],
    "verify": { "method": "GET", "path": "/cookies/sites", "expect": { "status": 200, "jsonHas": "sites" } }
  },
  {
    "id": "cookie-auto-resolve",
    "desc": "自动 cookie 拉取：无显式 cookie 时按域名回退 cookies/<label>.txt 过风控",
    "kind": "aux",
    "must_keep": true,
    "endpoints": [],
    "verify": { "manual": "cookies/ 放 bilibili.txt 后下载应自动带 --cookies；宿主勿屏蔽回退" }
  }
]
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | ✅ | 能力唯一标识（kebab-case） |
| `desc` | ✅ | 一句话说明 + **宿主接入时要做什么** |
| `kind` | ✅ | `core`（主能力）/ `aux`（辅助小功能）/ `invariant`（不变式，如 /health） |
| `must_keep` | ✅ | `true` = 接入中**不得丢失或被宿主屏蔽** |
| `endpoints` | ❌ | 该能力涉及的 HTTP 路径（宿主据此补代理） |
| `verify` | ✅ | 验收方式：可自动探测（`method`/`path`/`expect`）或 `manual`（人工核对） |

`verify.expect` 支持：`status`（状态码）、`jsonHas`（存在字段，支持点路径）、`jsonEquals`（字段等值）。
纯内部行为（无独立 endpoint，如自动回退/请求头注入）用 `verify.manual` 写清人工验收步骤。

### 10.2 自检脚本 `verify`（可执行 DoD）

每个模块必须附一个**读取自身 `capabilities[]` 并逐条真实探测**的自检脚本
（本机 HTTP 模块参考 `video_download/verify.mjs`，可整份复制后仅改 `module.json`）：

- 直连自检：`node verify.mjs`（从 `ports.json` / `local.defaultPort` 解析地址）
- **过宿主代理自检**：`node verify.mjs --base <宿主地址> --prefix <代理前缀>`
  —— 这一步专门用来发现「宿主漏代理某能力路径」的接入遗漏
- 任一 auto 探测失败 → 退出码 1；`manual` 项脚本会列出，接入时逐条人工确认
- 双击入口：`verify.bat`

### 10.3 接入工作流（人 / AI 通用）

1. 读目标模块 `capabilities[]`，**逐条**过一遍（不要只看主 endpoint）
2. `must_keep` 能力全部接通：补齐 `endpoints` 的宿主代理、UI 入口、参数透传
3. 直连跑 `verify` 全绿
4. 过宿主代理再跑 `verify --base <host> --prefix <前缀>` 全绿
5. `manual` 项按脚本提示确认
6. 全绿 + 人工项确认 = 接入完成

> 规则：凡是主 endpoint 之外的行为，**必须**登记进 `capabilities` 且给出 `verify`；
> 否则视为未按规范，接入方有权拒收。
