<div align="right"><sub>English: <a href="README.md">README.md</a></sub></div>

# AgenticX Decision：确定性决策审计工具架

这是一个基于 AgenticX 的本地优先决策审计工具架示例，用来演示如何把确定性规则留在代码中，让模型只处理有界上下文，并要求结论携带证据字段。当前校验检查结构和必要工具调用，尚未验证引用真实性或结论是否与工具一致。

> 研究原型。本仓库不包含客户文档、凭据或生产服务配置。Web 控制台只绑定本机地址，默认没有认证。

## 能做什么

- 用按需检索代替每次把全文发送给模型；
- 用手写规则工具执行数值、日期和字段存在性判断；
- 缺少工具调用、证据引用或合法 JSON 时阻断结论；
- 通过 SSE 控制台查看规则、工作区、结论、证据和 Token 用量；
- 使用离线 mock 模式运行完整链路，不需要 API Key。

引擎边界保持领域中立，可以通过替换规则规格和输入适配器，用于文档审核、采购评审等需要证据链的决策流程。

## 快速开始

需要 Python 3.10+ 和 Git。依赖只使用公开包与固定版本的上游 AgenticX 源码。

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

    # 离线链路检查和本地控制台，不访问网络，也不需要凭据。
    python mztdemo.py --mock
    python app.py --mock
    # 打开 http://127.0.0.1:8620

离线数据、规则和模型回答全部由 `sample_data.py` 人工构造，不是客户材料或实验实测。真实执行搜索和规则工具，但不能用于声称模型准确率、耗时或成本。控制台预置三条合成规则；自定义规则需在线运行。

配置示例见 `.env.example`，不会自动加载，需在终端 `export`；或运行 `python setup_key.py`。在线运行需要配置 `MZT_LLM_KEY`、`MZT_LLM_BASE_URL`、`MZT_LLM_MODEL` 与 `MZT_PDF`。端点 URL 不可内嵌凭据。`MZT_CONFIG_DIR` 可隔离本地配置。

验证：`python -m unittest discover -s tests -v`。跨文件演示：`python mztdemo_v2.py --mock`；全文基线：`python mztdemo_v3_baseline.py --mock`。真实跨文件运行需本地 PDF 包与视觉模型。成本工具内置单价为虚构算术样例，实际估算必须自行提供单价。

在线运行时通过环境变量或本地设置流程配置模型。不要提交 API Key、客户材料、模型响应或日志。控制台默认只监听 127.0.0.1，不要直接暴露到公网。

## 目录

- engine.py：检索、规则工具、AgenticX ReAct 执行、校验和 SSE 事件。
- app.py：本地 FastAPI 控制台。
- decomposer.py：把自然语言规则映射为结构化规格，不生成可执行代码。
- cost.py：根据本地运行日志重新计算用量和成本。
- docs/：面向公开读者的实验和扩展说明，示例使用合成数据。

## 数据与隐私

私有文档放在 data/，本地输出放在 results/，两者都被 Git 忽略。不要提交 PDF、截图、抽取文本、模型响应、日志、API Key 或端点凭据。凭据应通过环境变量或受限权限的本地文件提供。

这个项目不是访问控制层、合规认证或生产部署模板。处理敏感材料前，请单独评估威胁模型和权限边界。

## 许可证

Apache-2.0，见 LICENSE。

## 贡献

新增模型提供商、规则模板或数据适配器前请先开 Issue。贡献应包含离线测试，并且只能使用合成样例。
