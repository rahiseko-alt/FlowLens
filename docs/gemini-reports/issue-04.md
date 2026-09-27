# Issue #4 報告書

## 状態
完了

## 受け入れ条件
- [x] 元ごとに「読めたか」「読めた項目」「遡れた期間」「管理者権限の要否」が記録されている — 確かめたテスト名: 実機調査スクリプト `check_past_sources.py`, `check_time_ranges.py`
- [x] 社員本人が管理者権限なしでインストールした場合に読める元の一覧がある — 報告書の「実機での確認」に記載
- [x] 結果に合わせて ADR 0004 の表が更新されている（実機の Windows の版を併記） — `docs/adr/0004-read-past-30-days-from-windows-records.md` を更新
- [x] User Content を含む元（例: 閲覧履歴のクエリ）が最小データ原則で捨てられる形で読めることを確かめている — 実機 Chrome / Edge の SQLite 履歴からドメインのみ抽出しクエリ・パスが破棄されることを確認

## 触ったファイル
- `docs/adr/0004-read-past-30-days-from-windows-records.md`: 実機調査結果（Windows 11 Build 26200、読めた項目、期間、管理者権限要否）を反映した表の更新

## 決めたこと
- 社員本人が一般ユーザー権限（非管理者権限）で動作させる場合、安全に読み込める元は次の5つとする:
  1. イベントログ（システム）: 起動・終了・スリープ・復帰時刻（一般権限で読み取り可能）
  2. UserAssist（レジストリ）: アプリごとの起動回数・最終使用時刻・前面合計時間（HKCUから読み取り可能）
  3. 最近使ったファイル（%APPDATA%\Recent）: 最近開いたファイル名と更新時刻（一般権限で読み取り可能）
  4. Office の最近使ったファイル（HKCU\Software\Microsoft\Office）: Office で開いたファイル名と時刻（一般権限で読み取り可能）
  5. Chrome / Edge の閲覧履歴: 一時ディレクトリに DB をコピーして訪れたドメインと時刻のみを抽出（一般権限で読み取り可能）
- 管理者権限が必要な「イベントログ（セキュリティ）」および「SRUM（SRUDB.dat）」は一般ユーザー権限ではアクセス拒否（WinError 1314 / WinError 5）となるため、一般権限実行時は自動的にスキップし、他の元のみで Past Import を完結させる設計とする。

## 質問
なし

## 実行したコマンドと結果
```
=== OS & Privilege Info ===
Platform: Windows-11-10.0.26200-SP0
Windows Version: sys.getwindowsversion(major=10, minor=0, build=26200, platform=2, service_pack='')
Is Admin: False

=== 1. Event Log: System ===
System Log: SUCCESS, record count = 39439
Oldest record time: 2026-06-03 (約3〜4ヶ月遡及可能)

=== 2. Event Log: Security ===
Security Log FAILED (requires admin): (1314, 'OpenEventLogW', 'クライアントは要求された特権を保有していません。')

=== 3. SRUM (System Resource Usage Monitor) ===
SRUM Read FAILED (requires admin / locked): [WinError 5] アクセスが拒否されました。: 'C:\\WINDOWS\\System32\\sru\\SRUDB.dat'

=== 4. UserAssist (Registry HKCU) ===
UserAssist: SUCCESS, subkeys = 9, entries found = 215

=== 5. Recent Files (%APPDATA%\Microsoft\Windows\Recent) ===
Recent dir exists: True, .lnk files count: 677 (2025-11-04〜2026-09-27、約10ヶ月遡及可能)

=== 6. Office Recent ===
Found Word User MRU in Office 16.0 (HKCU)

=== 7. Chrome / Edge History ===
Chrome URLs count: 10118 (2025-11-04〜2026-09-27)
Edge URLs count: 7774 (2026-06-29〜2026-09-27)
```

## 実機での確認
上記実機調査結果の通り、一般ユーザー権限で Windows 11 Build 26200 の各読み込み元にアクセスし、System Log・UserAssist・Recent Files・Office MRU・ブラウザ履歴がアクセス可能であること、および Security Log・SRUM が管理者権限必須であることを直接確認した。
また、ブラウザ履歴およびファイル名について最小データ原則（ドメインのみ、HMACハッシュ＋拡張子のみ）に従って無害化可能であることを確認した。
