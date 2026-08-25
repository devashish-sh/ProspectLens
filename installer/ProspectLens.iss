; ProspectLens - Inno Setup Script
; Generates standalone ProspectLens-Setup.exe installer

#define MyAppName "ProspectLens"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "ProspectLens"
#define MyAppURL "http://localhost:8000"
#define MyAppExeName "ProspectLens.exe"
#define MyLauncherExeName "launcher_host.exe"

[Setup]
AppId={{D37E84B1-6E9C-4A2E-8B37-1234567890AB}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist_installer
OutputBaseFilename=ProspectLens-Setup
SetupIconFile=..\backend\icons\app.ico
UninstallDisplayIcon={app}\ProspectLens.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSmallImageFile=..\backend\icons\icon48.png
DisableWelcomePage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Engine binaries & PyInstaller internal assets
Source: "..\backend\dist\ProspectLens\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Chrome extension folder (excludes node_modules for clean, lightweight extension)
Source: "..\extension\*"; DestDir: "{app}\extension"; Excludes: "node_modules,package-lock.json"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start menu shortcuts
Name: "{autoprograms}\{#MyAppName}\ProspectLens Extension Folder"; Filename: "{win}\explorer.exe"; Parameters: """{app}\extension"""
Name: "{autoprograms}\{#MyAppName}\Uninstall ProspectLens"; Filename: "{uninstallexe}"
; Desktop shortcut (optional)
Name: "{autodesktop}\ProspectLens Extension Folder"; Filename: "{win}\explorer.exe"; Parameters: """{app}\extension"""; Tasks: desktopicon

[Registry]
; Register Native Messaging Host for Google Chrome
Root: HKCU; Subkey: "Software\Google\Chrome\NativeMessagingHosts\com.prospectlens.launcher"; ValueType: string; ValueName: ""; ValueData: "{app}\com.prospectlens.launcher.json"; Flags: uninsdeletekey

[Run]
; Option to open the extension folder immediately after installation
Filename: "{win}\explorer.exe"; Parameters: """{app}\extension"""; Description: "Open Chrome Extension folder (for loading unpacked in chrome://extensions)"; Flags: postinstall nowait skipifsilent

[Code]
// Helper function to escape backslashes for JSON strings
function EscapeJsonPath(const S: String): String;
var
  I: Integer;
  ResultStr: String;
begin
  ResultStr := '';
  for I := 1 to Length(S) do
  begin
    if S[I] = '\' then
      ResultStr := ResultStr + '\\'
    else
      ResultStr := ResultStr + S[I];
  end;
  Result := ResultStr;
end;

// Generate com.prospectlens.launcher.json dynamically with the actual install path
procedure CurStepChanged(CurStep: TSetupStep);
var
  ManifestPath: String;
  LauncherExePath: String;
  JsonContent: String;
begin
  if CurStep = ssPostInstall then
  begin
    LauncherExePath := EscapeJsonPath(ExpandConstant('{app}\launcher_host.exe'));
    ManifestPath := ExpandConstant('{app}\com.prospectlens.launcher.json');
    
    JsonContent := '{' + #13#10 +
      '  "name": "com.prospectlens.launcher",' + #13#10 +
      '  "description": "ProspectLens Backend Launcher Host",' + #13#10 +
      '  "path": "' + LauncherExePath + '",' + #13#10 +
      '  "type": "stdio",' + #13#10 +
      '  "allowed_origins": [' + #13#10 +
      '    "chrome-extension://foifgnnpaiflbngeinfjebgflnmhaibe/"' + #13#10 +
      '  ]' + #13#10 +
      '}';
      
    SaveStringToFile(ManifestPath, JsonContent, False);
  end;
end;
