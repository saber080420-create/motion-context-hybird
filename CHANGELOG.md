# Changelog

本项目遵循 [Semantic Versioning](https://semver.org/)。

## [1.0.0] - 2026-10-07

- 将 Motion Context 加载、应用、裁剪和保存链路封装为原生子图。
- 首段关闭续写时仍保存 latent。
- 后续段按上一段编号加载并继承 latent。
- 集中暴露项目名称、Clip 编号、继承帧数、帧率和尾部匹配参数。
- 输出到新 JSON，不修改源工作流。
