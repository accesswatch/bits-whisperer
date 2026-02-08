; ================================================================
; BITS Whisperer — Inno Setup Installer Script
; ================================================================
;
; BITS Whisperer is an accessible, privacy-first desktop application
; for audio transcription. It supports 17 transcription providers
; (cloud and on-device), full keyboard and screen reader support
; (NVDA, JAWS, Narrator), and runs on Windows 10 and later (64-bit).
;
; Prerequisites:
;   1. Build the app:  python build_installer.py --lean
;   2. Compile this:   iscc installer.iss
;
; Requires Inno Setup 6.0+ (https://jrsoftware.org/isinfo.php)
; ================================================================

#define MyAppName "BITS Whisperer"
#define MyAppVersion "1.2.0"
#define MyAppPublisher "Blind Information Technology Solutions (BITS)"
#define MyAppURL "https://github.com/accesswatch/bits-whisperer"
#define MyAppExeName "BITS Whisperer.exe"
#define MyAppCopyright "Copyright (C) 2025 Blind Information Technology Solutions (BITS)"
#define MyAppDescription "Accessible audio transcription with 17 providers"
#define MyAppContact "https://github.com/accesswatch/bits-whisperer/issues"

[Setup]
; Unique application identifier — do NOT change between versions
AppId={{7B3E8F2A-4D1C-4E9F-B6A5-2C8D7F9E1A3B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppContact}
AppUpdatesURL={#MyAppURL}/releases
AppCopyright={#MyAppCopyright}
AppComments={#MyAppDescription}
AppContact={#MyAppContact}
AppReadmeFile={app}\docs\README.html

; Installation directory
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}

; Require admin rights for Program Files installation
; Users may override to install per-user if they prefer
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

; License and info pages
LicenseFile=LICENSE
InfoBeforeFile=docs\ANNOUNCEMENT.md
InfoAfterFile=CHANGELOG.md

; Output settings
OutputDir=dist
OutputBaseFilename=BITS_Whisperer_Setup_{#MyAppVersion}
SetupIconFile=
; Uncomment below when icon is available:
; SetupIconFile=assets\icon.ico

; Compression — LZMA2/ultra64 for best compression ratio
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; Modern wizard style with slightly larger window for readability
WizardStyle=modern
WizardSizePercent=120

; Uninstaller
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}

; Minimum Windows version (Windows 10 build 17763 — version 1809)
MinVersion=10.0.17763

; 64-bit only — required for GPU acceleration and large model support
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Misc
DisableProgramGroupPage=auto
AllowNoIcons=yes
ShowLanguageDialog=auto
DisableWelcomePage=no

; Version info embedded in the Setup executable
VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup — Accessible Audio Transcription
VersionInfoCopyright={#MyAppCopyright}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoTextVersion={#MyAppVersion}

; Close running instances before upgrading
CloseApplications=force
CloseApplicationsFilter=*.exe
RestartApplications=no

; Allow previous installations to be detected and upgraded
UsePreviousAppDir=yes
UsePreviousTasks=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

; ----------------------------------------------------------------
; Custom messages — Welcome and Finish page text
; ----------------------------------------------------------------
[Messages]
WelcomeLabel1=Welcome to {#MyAppName}
WelcomeLabel2=This wizard will install {#MyAppName} v{#MyAppVersion} on your computer.%n%n{#MyAppName} is an accessible, privacy-first audio transcription application built by Blind Information Technology Solutions (BITS). It supports 17 transcription providers — including free on-device engines that require no internet connection.%n%nKey features:%n  - Full keyboard and screen reader support (NVDA, JAWS, Narrator)%n  - On-device transcription (Whisper, Vosk, Parakeet) — no cloud required%n  - 12 cloud providers (OpenAI, Google, Azure, AWS, and more)%n  - 7 export formats (Text, Markdown, HTML, Word, SRT, VTT, JSON)%n  - Batch processing with drag-and-drop%n%nIt is recommended that you close all other applications before continuing.
FinishedHeadingLabel=Installation Complete
FinishedLabel={#MyAppName} has been successfully installed on your computer.%n%nOn first launch, a Setup Wizard will guide you through:%n  - Hardware detection (CPU, RAM, GPU)%n  - Choosing Basic or Advanced mode%n  - Model recommendations and downloads%n  - Cloud provider configuration (optional)%n%nYour API keys are stored securely in Windows Credential Manager and never leave your machine.
ClickFinish=Click Finish to exit Setup. Check "Launch {#MyAppName}" below to start immediately.

; ----------------------------------------------------------------
; Tasks — what the user can choose during installation
; ----------------------------------------------------------------
[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut for {#MyAppName}"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "startmenu"; Description: "Create &Start Menu shortcuts (application, User Guide, uninstaller)"; GroupDescription: "Shortcuts:"; Flags: checkedonce
Name: "associate_wav"; Description: "Associate .&wav files with {#MyAppName} (Open With)"; GroupDescription: "File associations (optional):"; Flags: unchecked
Name: "associate_mp3"; Description: "Associate .&mp3 files with {#MyAppName} (Open With)"; GroupDescription: "File associations (optional):"; Flags: unchecked
Name: "associate_m4a"; Description: "Associate .m&4a files with {#MyAppName} (Open With)"; GroupDescription: "File associations (optional):"; Flags: unchecked
Name: "associate_flac"; Description: "Associate .&flac files with {#MyAppName} (Open With)"; GroupDescription: "File associations (optional):"; Flags: unchecked
Name: "install_copilot"; Description: "Install GitHub &Copilot CLI after setup (requires WinGet)"; GroupDescription: "Additional software:"; Flags: unchecked

; ----------------------------------------------------------------
; Files — application binaries, documentation, and license
; ----------------------------------------------------------------
[Files]
; Core application — everything from the PyInstaller dist folder
Source: "dist\BITS Whisperer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; License file (also installed alongside the exe for reference)
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion

; Documentation
Source: "CHANGELOG.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "docs\USER_GUIDE.html"; DestDir: "{app}\docs"; Flags: ignoreversion skipifsourcedoesntexist
Source: "docs\USER_GUIDE.md"; DestDir: "{app}\docs"; Flags: ignoreversion skipifsourcedoesntexist
Source: "docs\README.html"; DestDir: "{app}\docs"; Flags: ignoreversion skipifsourcedoesntexist
Source: "docs\ANNOUNCEMENT.html"; DestDir: "{app}\docs"; Flags: ignoreversion skipifsourcedoesntexist

; ----------------------------------------------------------------
; Registry — file associations (Open With context menu)
; ----------------------------------------------------------------
[Registry]
; .wav association
Root: HKCU; Subkey: "Software\Classes\.wav\OpenWithProgids"; ValueType: string; ValueName: "BITSWhisperer.wav"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate_wav
Root: HKCU; Subkey: "Software\Classes\BITSWhisperer.wav"; ValueType: string; ValueName: ""; ValueData: "Audio File — {#MyAppName}"; Flags: uninsdeletekey; Tasks: associate_wav
Root: HKCU; Subkey: "Software\Classes\BITSWhisperer.wav\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Flags: uninsdeletekey; Tasks: associate_wav

; .mp3 association
Root: HKCU; Subkey: "Software\Classes\.mp3\OpenWithProgids"; ValueType: string; ValueName: "BITSWhisperer.mp3"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate_mp3
Root: HKCU; Subkey: "Software\Classes\BITSWhisperer.mp3"; ValueType: string; ValueName: ""; ValueData: "Audio File — {#MyAppName}"; Flags: uninsdeletekey; Tasks: associate_mp3
Root: HKCU; Subkey: "Software\Classes\BITSWhisperer.mp3\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Flags: uninsdeletekey; Tasks: associate_mp3

; .m4a association
Root: HKCU; Subkey: "Software\Classes\.m4a\OpenWithProgids"; ValueType: string; ValueName: "BITSWhisperer.m4a"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate_m4a
Root: HKCU; Subkey: "Software\Classes\BITSWhisperer.m4a"; ValueType: string; ValueName: ""; ValueData: "Audio File — {#MyAppName}"; Flags: uninsdeletekey; Tasks: associate_m4a
Root: HKCU; Subkey: "Software\Classes\BITSWhisperer.m4a\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Flags: uninsdeletekey; Tasks: associate_m4a

; .flac association
Root: HKCU; Subkey: "Software\Classes\.flac\OpenWithProgids"; ValueType: string; ValueName: "BITSWhisperer.flac"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate_flac
Root: HKCU; Subkey: "Software\Classes\BITSWhisperer.flac"; ValueType: string; ValueName: ""; ValueData: "Audio File — {#MyAppName}"; Flags: uninsdeletekey; Tasks: associate_flac
Root: HKCU; Subkey: "Software\Classes\BITSWhisperer.flac\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Flags: uninsdeletekey; Tasks: associate_flac

; App Paths registration — allows launching from Run dialog (Win+R)
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{#MyAppExeName}"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{#MyAppExeName}"; ValueType: string; ValueName: "Path"; ValueData: "{app}"; Flags: uninsdeletekey

; ----------------------------------------------------------------
; Icons — Start Menu and Desktop shortcuts
; ----------------------------------------------------------------
[Icons]
; Start Menu shortcuts (grouped under BITS Whisperer folder)
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "Launch {#MyAppName} — accessible audio transcription"; Tasks: startmenu
Name: "{group}\User Guide"; Filename: "{app}\docs\USER_GUIDE.html"; Comment: "Open the {#MyAppName} User Guide in your browser"; Tasks: startmenu
Name: "{group}\What's New"; Filename: "{app}\docs\ANNOUNCEMENT.html"; Comment: "See what's new in {#MyAppName} v{#MyAppVersion}"; Tasks: startmenu
Name: "{group}\{#MyAppName} on GitHub"; Filename: "{#MyAppURL}"; Comment: "Visit the {#MyAppName} project on GitHub"; Tasks: startmenu
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"; Comment: "Remove {#MyAppName} from your computer"; Tasks: startmenu

; Desktop shortcut (optional — unchecked by default)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; Comment: "Launch {#MyAppName} — accessible audio transcription"

; ----------------------------------------------------------------
; Run — post-install actions
; ----------------------------------------------------------------
[Run]
; Option to launch BITS Whisperer after installation
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now (the Setup Wizard will guide you through first-time configuration)"; Flags: nowait postinstall skipifsilent
; Option to open the User Guide after installation
Filename: "{app}\docs\USER_GUIDE.html"; Description: "Open the User Guide in your browser"; Flags: nowait postinstall skipifsilent shellexec unchecked
; Install GitHub Copilot CLI via WinGet (if task was selected)
Filename: "winget"; Parameters: "install --id GitHub.Copilot --accept-source-agreements --accept-package-agreements"; Description: "Installing GitHub Copilot CLI..."; StatusMsg: "Installing GitHub Copilot CLI via WinGet..."; Flags: runhidden waituntilterminated skipifsilent; Tasks: install_copilot

; ----------------------------------------------------------------
; UninstallRun — clean up file associations on uninstall
; ----------------------------------------------------------------
[UninstallDelete]
; Clean up any leftover files in the install directory
Type: filesandordirs; Name: "{app}"
; Clean up downloaded SDK packages (if installed to app directory)
Type: filesandordirs; Name: "{app}\site-packages"

; ----------------------------------------------------------------
; Pascal Script — Custom installer logic
; ----------------------------------------------------------------
[Code]
// ---------------------------------------------------------------
// Check for running instances before installation
// ---------------------------------------------------------------
function IsAppRunning(): Boolean;
var
  ResultCode: Integer;
begin
  Result := False;
  if Exec('tasklist', '/FI "IMAGENAME eq ' + '{#MyAppExeName}' + '" /NH', '',
          SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    // tasklist returns 0 even if no match; we rely on CloseApplications
    Result := False;
  end;
end;

// ---------------------------------------------------------------
// Custom cleanup: offer to remove user data on uninstall
// ---------------------------------------------------------------
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
  ModelsDir: String;
  Msg: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\BITS Whisperer');
    if DirExists(DataDir) then
    begin
      // Check if models directory exists for a more specific message
      ModelsDir := DataDir + '\models';

      Msg := 'Do you want to remove your BITS Whisperer user data?' + #13#10 + #13#10;

      if DirExists(ModelsDir) then
        Msg := Msg + 'This will delete:' + #13#10 +
               '  - Downloaded transcription models (may be several GB)' + #13#10 +
               '  - Saved transcripts and job history' + #13#10 +
               '  - Application settings and preferences' + #13#10 +
               '  - Log files' + #13#10
      else
        Msg := Msg + 'This will delete:' + #13#10 +
               '  - Saved transcripts and job history' + #13#10 +
               '  - Application settings and preferences' + #13#10 +
               '  - Log files' + #13#10;

      Msg := Msg + #13#10 +
             'Your API keys (stored in Windows Credential Manager) will NOT be removed.' + #13#10 +
             'To remove API keys, use Windows Credential Manager before uninstalling.' + #13#10 + #13#10 +
             'Data directory: ' + DataDir;

      if MsgBox(Msg, mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(DataDir, True, True, True);
      end;
    end;
  end;
end;

// ---------------------------------------------------------------
// Display estimated disk space in the Ready page
// ---------------------------------------------------------------
function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo,
  MemoTypeInfo, MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result := '';

  if MemoDirInfo <> '' then
    Result := Result + MemoDirInfo + NewLine + NewLine;

  if MemoGroupInfo <> '' then
    Result := Result + MemoGroupInfo + NewLine + NewLine;

  if MemoTasksInfo <> '' then
    Result := Result + MemoTasksInfo + NewLine + NewLine;

  Result := Result + 'Additional information:' + NewLine +
    Space + 'BITS Whisperer stores user data in:' + NewLine +
    Space + Space + ExpandConstant('{localappdata}\BITS Whisperer') + NewLine +
    Space + 'API keys are stored securely in Windows Credential Manager.' + NewLine +
    Space + 'On-device models will be downloaded separately on first use.' + NewLine;
end;
