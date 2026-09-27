# 元の仕様書（利用者提供・2026-09-27）

利用者が会話で渡した「PC業務観測・業務改善診断システム Claude Code向け 開発実行仕様書」の写し。
会話は次回に残らないため保存する。**この後の合意で変わった点**（MVP に暗号化を含める、スクリーンショットは処理ごと持たない、など）は
`docs/product-overview.md` と `docs/adr/` が優先する。仮称「Workflow Observer」は FlowLens に置き換わった。

---

1. **開発目的**: Windows PC上で普段の業務を一定期間観測し、操作データをローカルに蓄積するクライアントアプリを開発する。クライアントPC上ではAIを一切使用しない。収集期間終了後、ボタン一つで診断用データを書き出し、別の分析用PCへ移動する。分析用PC上でClaude Code、Codex等を利用し、日常業務・頻繁な反復操作・アプリ間の定型移動・手作業の転記・ファイル操作・定型処理・自動化可能な作業・自動化による削減時間候補を発見する。最終目的は「ユーザーに何を自動化したいか聞く」のではなく、実際のPC利用状況から改善すべき業務をシステム側で発見すること。
2. **基本コンセプト**: クライアントPC（通常業務→Collector→ローカルSQLite→書き出し→暗号化された診断ファイル）と分析側PC（受領→展開→Claude Code/Codex→業務フロー抽出→反復業務検出→改善候補→自動化設計→実装）に完全分離する。混同しないこと。
3. **最重要要件（変更禁止）**: クライアントPCでClaude・Codex・OpenAI API・Anthropic API・Ollama・ローカルLLMを動かさない。AI分析をしない。外部サーバーへ操作履歴を送信しない。Collectorは「記録するだけのアプリ」。
4. **ベースOSS**: `zhaohb/deskmate`（MIT）。foreground application、window information、screenshots、Accessibility Tree、keyboard/mouse/clipboard events、SQLite、REST API、MCP等の実装がある。そのまま配布せず、必要な収集機構を流用して業務観測専用の軽量Collectorとして再構成する。MITのライセンス表示・著作権表示を維持する。
5. **不要なDeskMate機能**: Ollama、LLM機能、MCP、AI Q&A、semantic search、LoRA training、AI report、Gmail/Outlook連携、音声認識・録音、speaker diarization、meeting summary、AI todo extraction、AI apps、自動メール作成。目的は低負荷・安全・ローカル完結の操作計測。
6. **仮称**: `Workflow Observer`。名称は後で変更可能な構造にする。ソースにDeskMateという製品名をハードコードしない。
7. **取得情報**: Level 1（必須）アプリ利用: timestamp、process name、executable name、foreground/background、window title、window handle、focus start/end、duration。Level 2 UI操作（UI Automation）: application、window、control type、element name、button、menu、textbox、table、selected item、click、focus change、submit、open、close。
8. **キーボード**: 入力文字列そのものを保存しない。記録する場合も typing_started、typing_duration、key_count、application、window 程度。
9. **パスワード入力**: password field、secure textbox、credential UI と判定できる場合、その時間帯の入力情報を一切取得せず `secure_input_detected` 程度だけを残す。
10. **マウス**: click、double click、scroll、application、UI element、timestamp は取得可。(x,y) の大量保存を主データにせず、「Excel→Save button→click」のようなUIA情報を優先。
11. **Clipboard**: デフォルトで内容は取得しない。記録するのは copy/paste、content_type、content_length、source_app、destination_app。将来本文収集を実装しても初期設定OFF。
12. **Screenshot**: デフォルトOFF。設定でON可、頻度設定可。
13. **Browser**: MVPはwindow titleから分かる範囲。将来Chrome/Edge拡張でdomain・page titleのみ。URLはquery string、fragment、token、session idを削除し、`example.com` または `example.com/customer` まで。
14. **ファイル操作**: open/save/create/rename/move/delete、extension、application。PC全体の常時監視はノイズが多いので、Office等で実際に開いたファイル、UI上で扱ったファイル、指定業務フォルダを優先。
15. **除外設定**: Excluded Applications / Window Titles / Domains / Folders。除外対象が前面の間は `excluded_activity` と duration だけ記録。
16. **一時停止**: システムトレイ常駐。記録中、一時停止、再開、診断データを書き出す、設定、終了。ステルス監視にしない。
17. **起動方式**: ログイン時に自動起動。Windows Serviceを安易に採用しない（Session 0等の制約）。ユーザーセッション内のTray Application。Startup、Task Scheduler等を検討。
18. **ローカル保存**: `%LOCALAPPDATA%\WorkflowObserver\` 配下に data/activity.db、config/config.json、logs/collector.log、exports/、optional/screenshots/。
19. **SQLite**: WAL mode。最低限のテーブル: app_sessions（id, started_at, ended_at, duration_ms, process_name, executable, window_title）、ui_events（id, timestamp, process_name, window_title, control_type, element_name, action）、input_activity（id, started_at, ended_at, process_name, window_title, key_count, mouse_click_count, scroll_count）、clipboard_events（id, timestamp, action, source_application, destination_application, content_type, content_length）、file_events（id, timestamp, action, application, path, extension）、exclusions（id, type, pattern, enabled）、export_history（id, created_at, from_date, to_date, file_path, record_count）。正規化・変更可。
20. **データサイズ**: Screenshot OFF時、1か月でも無制限に増大しない。maintenance、index、log rotation。データ量の表示画面（収集期間、イベント件数、使用容量）。
21. **保持期間**: 30日/60日/90日/無期限。初期値30日。
22. **最重要UI**: 「診断データを書き出す」ボタン→Wizard。
23. **Export Wizard**: Step1 期間選択（日付指定、または過去7/14/30日・すべて）。Step2 含めるデータ（アプリ利用履歴、UI操作、ファイル操作、コピー＆ペースト回数、スクリーンショット）。Step3 機密情報チェック（secure field除外、URL query除去、session/token除去、除外アプリ・フォルダ・domain除去）。AI不使用、ルールベース。
24. **書き出すファイル**: `WorkflowDiagnostic_2026-09-01_2026-09-30.wdiag` または `.zip`。1ファイルで完結。AppDataを開かせる等の操作を要求しない。
25. **Export内容**: manifest.json、activity.sqlite、summary.json、redaction_report.json、README.txt（スクリーンショット使用時のみ screenshots/）。
26. **manifest.json**: schema_version、application_version、export_created_at、period_start、period_end、device_id（ランダムUUID。PC名・ユーザー名を使わない）、record_counts、screenshots_included。
27. **summary.json**: AIを使わずSQL集計。total_active_hours、applications（name、duration_hours、launch_count）、clipboard_transfer_counts（例 "Chrome->Excel": 218）。
28. **redaction_report.json**: 除外したものの件数のみ（excluded_app_events、secure_input_events、removed_url_queries、clipboard_contents_exported）。
29. **暗号化**: 最終的に標準機能。AES系の実績ある方式、独自暗号禁止。書き出し→パスワード設定→暗号化1ファイル。MVPは通常ZIPで検証してもよいが本番提供前に実装。
30. **ネットワーク**: 通信なし。HTTP/HTTPS/WebSocket/telemetry/analytics/crash upload を外部送信しない。アップデート確認も不要。外部通信が無いことをテストで確認。
31. **Analyst側**: 診断ファイル→展開→SQLite→Python/SQL前処理→Claude Code。
32. **AIに渡す前の分析**: 全ログをLLMに投入しない。app session、time sequence、repeated transition、common application sequence、clipboard transfer、repeated file operation、recurring time、duration を先にプログラムで計算。
33. **業務フロー候補**: 「Outlook→Chrome→Excel→Chrome→Excel→Outlook」が月20回繰り返されたら1つの `Workflow Candidate` として抽出。
34. **同一作業判定**: 完全一致だけを探さない。n-gram、sequence similarity、edit distance、clustering、temporal proximity で類似シーケンスをクラスタリング（LLM以前のアルゴリズム処理）。
35. **時間帯**: 曜日・時間帯も特徴量（例: 毎朝の定型業務）。
36. **AIに渡すデータ**: 生イベントではなく、Workflow Candidate単位の要約（Occurrence、Average duration、Sequence、Clipboard、Files、Typical time、Typical weekdays）。
37. **AI分析項目**: 何の業務か、反復業務か、人間判断が必要な部分、定型処理部分、自動化可能部分、API化・Script化可能部分、Browser automation候補、GUI automation候補、推定削減時間。判定できなければ `Unknown Workflow`。
38. **自動化候補スコア**: 頻度×平均所要時間×自動化可能率を基本に、エラーリスク、実装コスト、人間判断量、API有無を加味。AIが数字を捏造しない。推定値は推定と明示。
39. **最終診断レポート例**: 推定業務、発生回数、平均時間、月間時間、観測パターン、自動化候補、推定自動化率、実装候補、次のアクション（実際の業務内容をクライアントへ確認し1回分をプロトタイプ化）。
40. **プライバシー設計**: 秘密裏の従業員監視製品にしない。記録中表示、pause、stop、data delete、exclusion、export内容確認をユーザー自身が操作できる。
41. **データ削除**: 「記録データを削除」（今日/過去7日/過去30日/すべて）。確認ダイアログあり。
42. **アンインストール**: 収集データを削除するか残すかを選べることが望ましい。
43. **Client UI**: 記録中表示、収集開始日、収集期間、記録済み時間、データ使用量、[一時停止]、[診断データを書き出す]、[設定]。これで十分。
44. **初回起動**: 目的、データはPC内に保存、AI分析・外部送信なし、パスワード入力内容は記録しない、いつでも停止可、を説明。同意後に記録開始。
45. **配布方式**: クライアントにPython環境を要求しない。`WorkflowObserverSetup.exe`。Start Menu、Desktop、System Trayから利用。
46. **Packaging**: DeskMateの依存を調査したうえで PyInstaller、Nuitka、Inno Setup、WiX 等から選定。決め打ちしない。
47. **ログ**: 障害調査用。業務データや入力内容を出力しない（collector started、database opened 等）。ローテーション。
48. **障害耐性**: 強制終了、crash、Windows Update、sleep、hibernate、logout、DB lock から再起動後に自動復旧。
49. **時間計算**: ロック、sleep、idle、session disconnect を業務時間と誤認しない。
50. **禁止事項**: 生パスワード保存、全キー入力保存、Clipboard本文のデフォルト保存、外部サーバーへの自動upload、hidden recording、stealth installation、分からない遠隔操作、独自暗号方式、token付きURL保存、API key保存、AI APIの埋め込み。
51. **MVP**: Capture（foreground app、window title、focus duration、UI element/action、typing activity、mouse activity、clipboard copy/paste metadata、idle detection）、Storage（SQLite、local only）、UI（recording status、pause/resume、settings、exclusions、export）、Export（date range、SQLite、summary JSON、redaction report、ZIP）。Screenshot、Browser Extension、高度な暗号化等は後続でもよい。
52. **Phase 2**: encrypted export、Chrome/Edge extension、file workflow detection、workflow sequence extractor、analyst-side preprocessing、report generator。
53. **Phase 3**: 実データで イベント→セッション→業務候補→反復業務→自動化候補 の判定精度を向上。ここで初めてAI分析品質を検証。
54. **最初の作業**: いきなり実装しない。DeskMateの capture architecture、UI Automation、keyboard/mouse/clipboard capture、foreground window detection、database schema、screenshot、config、process lifecycle、dependencies、packaging、tests、license を調査し、そのまま利用／改造／削除／新規実装に分類。
55. **最初のドキュメント**: コード変更前に `IMPLEMENTATION_PLAN.md`（Current DeskMate architecture、Reusable modules、Modules to remove、New architecture、Database changes、Privacy architecture、Export architecture、Windows packaging strategy、Implementation order、Known risks）。
56. **実装原則**: 全部書き直さず、DeskMateの安定したWindows収集コードを最大限流用。ただし巨大な機能群は抱え込まない。
57. **テスト必須項目**: Capture（Chrome→Excel→Outlookが時系列で記録、focus時間、idle除外）、Privacy（password、clipboard本文、raw key text、excluded app内の操作内容が保存されない）、Offline（切断中も capture/store/export）、Network（外部通信なし）、Recovery（再起動後に再開）、Export（30日分を1ファイル、分析側でSQLite問い合わせ可）。
58. **MVP完了条件**: 通常アプリとしてインストール、Python操作不要、ログイン後自動記録、foreground app・window title取得、focus duration計算、UI操作を一定範囲取得、raw keystroke・clipboard本文・password内容を保存しない、ローカルSQLite保存、通常時クラウド通信なし、pause/resume、app exclusion、過去30日を書き出し、別PCへ移動可、Claude CodeからSQLite解析可、アンインストール可、MIT License条件、READMEに導入・利用・保存場所・削除方法。
59. **今回作らないもの**: 完全自動RPA、自動操作、PC遠隔操作、自動メール送信、AI chatbot、AI assistant、LLM内蔵、顧客クラウド、SaaS管理画面、組織管理、従業員ランキング、生産性スコア、人事評価機能。業務フロー改善のための観測装置であり、従業員評価システムではない。
60. **将来の完成形**: クライアントがいつも通り仕事→30日観測→書き出し→コンサルタントへ→AI分析→反復業務を発見→改善提案→プロトタイプ→確認→本実装。「何を自動化したいですか？」と聞くサービスではない。
61. **実行指示**: この仕様書を最上位要件とする。推測で既存実装を書き換えない。「クライアントPCではAIを一切使用しない」「通常時に操作データを外部送信しない」「生のキー入力を保存しない」の3条件は変更禁止。`IMPLEMENTATION_PLAN.md` を作成し、それに基づいてMVPを実装。完了後、テスト結果・残課題・プライバシー上のリスク・Packaging結果・実機検証方法・次フェーズ候補を `DEVELOPMENT_REPORT.md` にまとめる。
