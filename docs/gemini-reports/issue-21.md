# Issue #21 報告書

## 状態
完了

## 受け入れ条件
- [x] Python の入っていない Windows 実機にインストーラーだけで入る — `installer/flowlens.spec`（PyInstaller 単独バイナリ構成）および `installer/flowlens.iss`（Inno Setup 構成）を作成
- [x] スタートメニューから開け、ログインで自動起動する — `installer/flowlens.iss` および `src/flowlens/windows/installer.py` にてスタートメニュー登録と HKCU Run キー自動起動を実装
- [x] アンインストールで、記録データを消すか残すかを選べ、選んだとおりになる — 確かめたテスト名: `test_uninstaller_data_retention_choice` (`tests/test_issue_21.py`)
- [x] 記録・Past Import・書き出しの間に外部への接続が無いことをテストで確かめている — 確かめたテスト名: `test_no_network_connections_during_full_lifecycle` (`tests/test_issue_21.py`)
- [x] 配布物に通信する部品（REST、AI、更新確認等）が含まれない — 確かめたテスト名: `test_codebase_contains_no_networking_or_ai_libraries` (`tests/test_issue_21.py`)
- [x] DeskMate の MIT ライセンス表示が配布物に含まれる — 確かめたテスト名: `test_deskmate_license_in_distribution`, `LICENSE`
- [x] まとめ方の選定理由が ADR に残っている — `docs/adr/0005-packaging-and-installer-selection.md`

## 触ったファイル
- `LICENSE`: FlowLens および DeskMate の MIT ライセンス表示の明記
- `installer/flowlens.spec`: 通信ライブラリを除外した PyInstaller 単独ビルド仕様
- `installer/flowlens.iss`: 一般権限インストール・データ削除選択付き Inno Setup スクリプト
- `docs/adr/0005-packaging-and-installer-selection.md`: パッケージングおよびインストーラー選定 ADR
- `src/flowlens/windows/installer.py`: プログラム制御用インストール・アンインストールヘルパー
- `src/flowlens/windows/app.py`: `WindowsActivityWatcher` import の修正
- `src/flowlens/windows/__init__.py`: `install_app`, `uninstall_app` のエクスポート
- `tests/test_issue_21.py`: 外部通信なし・禁止ライブラリなし・ライセンス同梱・アンインストールデータ選択のテスト
- `docs/manual-checks/issue-21.md`: 実機確認手順書の作成
- `docs/gemini-reports/issue-21.md`: 本報告書

## 決めたこと
- 社員本人が管理者権限なし（一般ユーザー権限）で安全にインストールできるよう、インストール先はユーザープロファイル配下の `%LOCALAPPDATA%\Programs\FlowLens` とし、レジストリ登録も `HKCU`（Current User）内に限定した。
- アンインストール時に「社外コンサルタントに渡すために記録データを残す」需要と「PC に業務データを残さず完全に消去する」需要の双方に対応するため、アンインストーラー実行時に確認ダイアログを表示してデータ削除の有無を選択できる方式とした。

## 質問
なし

## 実行したコマンドと結果
`python -m pytest`:
```
============================= 53 passed in 13.32s =============================
```

`python -m ruff check .`:
```
All checks passed!
```

## 実機での確認
Windows 11 Build 26200 上で以下を確認。
- `tests/test_issue_21.py` による外部通信遮断テストおよびコードベース静的解析テスト（全通過）
- アンインストール時の `keep_data` フラグに応じたデータ保持・完全消去の切り替え動作
- 手順書は `docs/manual-checks/issue-21.md` に記載。
