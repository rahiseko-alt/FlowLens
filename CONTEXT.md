# FlowLens

普段の PC 操作から業務フローの構造を復元し、反復業務・非効率な業務・自動化候補を後段の AI に発見させるための観測装置。操作の記録そのものではなく、作業の「順序・時間・繰り返し」を扱う。

## 二つの側

**Collector**:
クライアント PC 上で動き、操作を観測・正規化してローカルに保存し、診断ファイルとして書き出すアプリ。AI を一切含まない。
_Avoid_: Logger, エージェント, 監視ツール, Workflow Observer（旧仮称）

**Analyst 側**:
診断ファイルを受け取った別 PC で、プログラムと AI を使って業務フローを発見する工程。
_Avoid_: サーバー, クラウド

**Client PC**:
Collector を入れて普段どおり業務を行う PC。
_Avoid_: 端末, 従業員 PC

**社員**:
Client PC を使い、自分で Collector をインストールし、診断ファイルを書き出して渡す人。
_Avoid_: ユーザー, 従業員, 被観測者

**コンサルタント**:
Analyst 側で診断ファイルを分析し、業務改善の候補をまとめる人。通常は開発者本人だが、別の人が担うこともある。
_Avoid_: アナリスト, 分析者, 管理者

## 観測するもの

**Activity Event**:
Collector が保存する一件の操作記録。何を・どのアプリで・いつ行ったかの構造だけを持ち、書かれた内容は持たない。
_Avoid_: ログ, キーログ

**App Session**:
あるアプリ（ウィンドウ）が前面にあった一続きの期間。idle・ロック・スリープの時間を含まない。
_Avoid_: 利用時間, フォーカス

**Operation Type**:
操作の種類。クリック、フォーカス移動、Copy / Cut / Paste、Enter / Tab / Escape、ショートカット起動、入力の発生など。入力された文字は含まない。
_Avoid_: キー入力, keystroke

**Typing Activity**:
入力が発生したという事実と、その回数・継続時間。文字や文章、IME の確定内容は含まない。
_Avoid_: 入力内容, テキスト

**Clipboard Transfer**:
Copy / Cut と Paste の組で表す、アプリ間の転記。どのアプリからどのアプリへ、どの種類・長さのデータが移ったかだけを持つ。
_Avoid_: クリップボード内容, コピー履歴

**Control Metadata**:
操作された UI 部品の種別と識別情報（ControlType、AutomationId、ClassName、FrameworkId、状態）。部品に表示・入力された内容は含まない。
_Avoid_: UIA Tree, 画面テキスト

**User Content**:
ユーザーや業務が生み出した中身。入力欄の値、本文、Clipboard の中身、顧客名などを指す。Collector は永続保存しない。
_Avoid_: データ, テキスト

**Live Capture**:
同意した時点から先の操作を、Collector が記録し続けること。
_Avoid_: 監視, 未来の記録

**Past Import**:
同意した時点で、Windows や各アプリが既に残している過去30日分の記録を読み込むこと。Live Capture より粒度が粗く、両者は区別して保存する。
_Avoid_: 過去ログ収集, 遡及監視

## 書き出しと分析

**Diagnostic Export**:
Collector が指定期間のデータを除外・無害化したうえで一つにまとめたファイル。Client PC から Analyst 側へ渡る唯一の経路。
_Avoid_: バックアップ, ログファイル, ダンプ

**Operation Sequence**:
時間順に並べた App Session と Activity Event の列。業務フローを発見する素材。
_Avoid_: 操作ログ, 履歴

**Workflow Candidate**:
Analyst 側で、似た Operation Sequence が繰り返し現れたものを一つにまとめた業務候補。何の業務か判定できないものは Unknown Workflow とする。
_Avoid_: 業務, タスク, パターン
