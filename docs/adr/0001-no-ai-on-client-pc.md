# Client PC では AI を一切動かさず、分析は Analyst 側だけで行う

Collector は観測・正規化・ローカル保存・書き出しだけを行い、LLM、ローカルモデル、外部 AI API、MCP を含まない。通常の利用中に操作データを外部へ送らない。AI による分析は、Diagnostic Export を受け取った Analyst 側で初めて行う。Client PC には業務情報がそのまま載っているため、AI や通信を持ち込むと漏えいの経路と利用者の不安が増える。これに対して、分析の賢さは Analyst 側だけで上げられる。

## Consequences

- 流用元の DeskMate にある Ollama、MCP、REST、AI アプリ群は、Collector へは持ち込まない。
- 「外部へ通信していないこと」はテストで確かめる対象になる。
