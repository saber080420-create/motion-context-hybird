# ComfyUI H3 Motion Context UX

面向 MiniMax H3 Motion Context 工作流的易用性改造：把复杂的续写节点封装成一个主节点，并为 latent 编号管理增加视频反查和覆盖保护。

## 为什么做这个项目

原始 Motion Context 工作流需要手动管理多个加载、继承、裁剪和保存节点。制作同一段内容的多个版本时，视频文件可以使用有意义的名称，但 latent 通常只能按 `1、2、3…` 编号保存，时间一长很容易混淆视频与 Clip 编号的对应关系。

本项目把高频操作收敛成面向新手的工作流和辅助节点。

```mermaid
flowchart LR
    A[v1：封装续写链路] --> B[v2：视频反查 Clip]
    B --> C[编号占用检查]
    C --> D[用户确认后覆盖]
```

## 版本

### v1.0.0：Motion Context 一键续写

- 将分散的 Motion Context 节点封装为原生子图；
- 首段关闭续写时仍保存 latent；
- 第二段开始自动加载、继承和裁剪上一段 latent；
- 保留“上一段编号”和“本段编号”手动控制。

### v2.0.0：编号查询与覆盖保护

- 新增 `Latent 编号查询` 节点；
- 支持从 ComfyUI 输出目录选择视频；
- 支持上传本地视频，上传后由用户点击“查询”；
- 优先读取视频内嵌工作流元数据，输出目录视频可回退读取 VHS 伴随 PNG；
- 显示对应 Clip 编号和 latent 路径；
- 采样前检查“本段编号”是否已被占用；
- 默认拒绝覆盖，用户开启“允许覆盖已有 latent”后才放行；
- 查询工具只提供信息，不自动改写主节点的“上一段编号”。

## 安装

### 1. 安装辅助节点

在 ComfyUI 的 `custom_nodes` 目录执行：

```bash
git clone https://github.com/saber080420-create/motion-context-hybird.git
```

重启 ComfyUI。

### 2. 导入工作流

将下列文件拖入 ComfyUI：

- [`workflows/白膜奔跑加强_MC一键续写_v1.json`](workflows/白膜奔跑加强_MC一键续写_v1.json)
- [`workflows/白膜奔跑加强_MC一键续写_v2.json`](workflows/白膜奔跑加强_MC一键续写_v2.json)

新项目建议直接使用 v2。详细操作见：

- [`docs/v1-使用说明.md`](docs/v1-使用说明.md)
- [`docs/v2-使用说明.md`](docs/v2-使用说明.md)

## 查询逻辑

### 输出目录视频

1. 在“从下拉框选择视频”中选择视频；
2. 点击“查询”；
3. 节点读取内嵌工作流元数据；
4. 如果视频没有内嵌元数据，则尝试读取同名或同时间生成的 VHS PNG；
5. 显示 Clip 编号及 latent 路径。

### 本地视频

1. 点击“上传本地视频”；
2. 节点显示“已上传，等待查询”；
3. 点击“查询”；
4. 节点读取上传视频自身的内嵌工作流元数据。

经过剪辑、转码或平台下载后，视频内嵌元数据可能丢失，此类文件无法可靠反查。上传文件只允许从 ComfyUI `input` 目录读取，输出视频和 latent 只允许从 `output` 目录读取。

## 运行环境

工作流基于 MiniMax H3 视频生成环境整理，需要自行安装工作流中使用的模型和对应自定义节点，包括 Motion Context、Video Helper Suite 及工作流内显示的 H3 相关节点。

辅助节点使用 ComfyUI 自带的 Python 环境，并在可用时复用 Video Helper Suite 或 `imageio-ffmpeg` 提供的 ffmpeg。

## 项目边界

本项目只改善工作流交互、编号查询和覆盖保护，不修改 MiniMax H3 或 Motion Context 的生成算法。

## 更新记录

见 [`CHANGELOG.md`](CHANGELOG.md)。
