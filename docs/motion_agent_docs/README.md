# Motion Agent HTML 文档集

此目录保存本次整理的 Motion Agent 文档、原始文本和原图。

- `index.html`：文档入口。
- `01_agent_log_trace_memory_planning.html`：日志、Trace、Memory、Planning 与 Skills 规划原文。
- `02_complex_task_orchestration.html`：复杂自然语言任务编排设计原文。
- `03_robot_mcu_integration_test_20260721.html`：2026-07-21 真机 MCU 联调报告原文。
- `04_motion_agent_architecture_and_prediction.html`：Motion Agent 总体路由与下一任务预判规则。
- `sources/`：未经改写的附件原文，以及单独整理的总体架构文本。
- `assets/`：用户提供的三张原始流程图及页面样式、脚本。

页面不依赖外部 CDN。因为浏览器通常不允许 `file://` 页面通过 `fetch()` 读取相邻文本，请从仓库根目录启动静态服务器：

```bash
python -m http.server 8080
```

然后打开：

```text
http://127.0.0.1:8080/docs/motion_agent_docs/
```

每页都可在“整理视图”和“完整原文”之间切换。附件中没有实际提供的 `[图片]` 仍保留为占位说明，不用其他图片冒充。
