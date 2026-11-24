; Instalador de Radar de Tendencias Pro (Inno Setup 6)
; GitHub Actions lo compila solo. Para compilarlo a mano en Windows:
;   1) pyinstaller ... (ver .github/workflows/instalador.yml)
;   2) "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DMyAppVersion=1.0.0 instalador\RadarTendenciasPro.iss

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppName "Radar de Tendencias Pro"
#define MyAppExe "RadarTendenciasPro.exe"
#define MyAppPublisher "Obsidiana Technology"
#define MyAppURL "https://danimakerbro-cloud.github.io/radar-tendencias-pro/"

[Setup]
; No cambies AppId: así Windows reconoce las actualizaciones como el mismo programa.
AppId={{8F3C2A71-5B4E-4D9A-9C61-2E7A0B5D41F3}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
VersionInfoVersion={#MyAppVersion}
DefaultDirName={autopf}\Radar de Tendencias Pro
DefaultGroupName=Radar de Tendencias Pro
DisableProgramGroupPage=yes
; Se instala sin pedir permisos de administrador (en la carpeta del usuario).
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\salida
OutputBaseFilename=RadarTendenciasPro-Setup
SetupIconFile=..\radar.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\RadarTendenciasPro\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LEEME.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autoprograms}\Léeme - {#MyAppName}"; Filename: "{app}\LEEME.txt"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
