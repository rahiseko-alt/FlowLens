; Inno Setup Script for FlowLens Collector
; Installs per-user without administrative privileges into %LOCALAPPDATA%\Programs\FlowLens

#define MyAppName "FlowLens"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "FlowLens Team"
#define MyAppExeName "flowlens.exe"

[Setup]
AppId={{D37F2C5A-9D4A-4B6A-91E2-5F8A2D4E3C1B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=flowlens_installer
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "..\dist\flowlens\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Registry]
; Configure auto-start on user login
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "FlowLens"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue

[Code]
// Custom uninstallation prompt: ask whether to keep or delete recorded data
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\FlowLens');
    if DirExists(DataDir) then
    begin
      if MsgBox('記録データ（' + DataDir + '）も完全に消去しますか？'#13#10#13#10 +
                '［はい］: すべての記録データを削除します。'#13#10 +
                '［いいえ］: データは残し、分析に利用できるようにします。',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(DataDir, True, True, True);
      end;
    end;
  end;
end;
