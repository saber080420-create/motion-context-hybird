# ComfyUI H3 Motion Context UX

面向 MiniMax H3 Motion Context 工作流的易用性改造项目。

## v1.0.0：一键续写工作流

v1 将分散的 Motion Context 节点封装为一个原生子图，减少新手需要理解和连接的节点数量。

主要功能：

- 首段关闭续写时仍保存 latent；
- 从第二段开始加载上一段 latent；
- 自动完成继承、裁剪和下一段保存；
- 保留“上一段编号”和“本段编号”手动控制。

## 使用方式

1. 下载 [`workflows/白膜奔跑加强_MC一键续写_v1.json`](workflows/白膜奔跑加强_MC一键续写_v1.json)。
2. 将工作流导入 ComfyUI。
3. 按照 [`docs/v1-使用说明.md`](docs/v1-使用说明.md) 配置项目名称和 Clip 编号。

该工作流基于作者本地的 MiniMax H3 视频生成环境整理，使用前需要安装工作流中对应的 H3、Video Helper Suite 及相关自定义节点和模型。

## 版本计划

后续版本将围绕 latent 编号管理、占用检查和视频反查继续改进。
