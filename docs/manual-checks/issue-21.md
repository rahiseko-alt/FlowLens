# Issue #21 実機確認手順書: インストーラー・アンインストーラーと通信なしの確認

この手順書は、Windows 実機において FlowLens の単独実行ファイル化（PyInstaller）、一般権限インストーラー（Inno Setup）、アンインストール時のデータ保持選択、および外部通信がないことを確認する手順です。

## 前提条件
- OS: Windows 10 または Windows 11
- Python 3.12 (ビルド検証用)
- 実行権限: 一般ユーザー権限（管理者権限不要）

## 確認手順

1. **PyInstaller による単独バイナリのビルド確認**
   リポジトリルートで以下を実行し、ビルド定義（`installer/flowlens.spec`）が構文エラーなく解析されることを確認します。
   ```bash
   pyinstaller installer/flowlens.spec --dry-run
   ```
   - [x] 通信ライブラリ（`requests`, `httpx`, `aiohttp`, `fastapi`, `openai` 等）が `excludes` により完全に除外されていること。
   - [x] `LICENSE` ファイル（DeskMate MIT ライセンス表示を含む）が配布物同梱データ（`datas`）に含まれていること。

2. **Inno Setup スクリプトの検証**
   `installer/flowlens.iss` を確認します。
   - [x] `PrivilegesRequired=lowest` が設定されており、管理者権限なしで `%LOCALAPPDATA%\Programs\FlowLens` にインストールされること。
   - [x] スタートメニュー（`{autoprograms}`）および HKCU Run レジストリキーに登録されること。
   - [x] アンインストール時に Pascal スクリプト（`CurUninstallStepChanged`）により、記録データ（`%LOCALAPPDATA%\FlowLens`）を「消去する」か「残す」かをユーザーに確認するダイアログが表示されること。

3. **アンインストール時のデータ保持動作の確認**
   Python の `flowlens.windows.installer.uninstall_app` を呼び出して動作を確認します。
   ```python
   from flowlens.windows.installer import uninstall_app
   # データを残す場合
   uninstall_app(target_dir=install_path, data_dir=data_path, keep_data=True)
   # データを完全削除する場合
   uninstall_app(target_dir=install_path, data_dir=data_path, keep_data=False)
   ```

4. **外部通信なしの確認**
   `tests/test_issue_21.py` の `test_no_network_connections_during_full_lifecycle` および `test_codebase_contains_no_networking_or_ai_libraries` を実行し、ライフサイクル全体で socket 接続や外部通信が一切発生しないこと、コードベース内に通信ライブラリの import が存在しないことを確認します。
