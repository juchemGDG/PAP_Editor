; Inno Setup Skript für den PAP Editor (Windows-Installer)
; Erzeugt dist\PAP-Editor-Setup.exe
; Aufruf:  iscc packaging\pap_editor.iss   (nach dem PyInstaller-Build)

[Setup]
AppName=PAP Editor
AppVersion=1.0.0
AppPublisher=GDG Stuttgart
DefaultDirName={autopf}\PAP Editor
DefaultGroupName=PAP Editor
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=PAP-Editor-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
; SetupIconFile=icon.ico

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[Files]
; der komplette PyInstaller-Ausgabeordner
Source: "..\dist\PAP-Editor\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PAP Editor"; Filename: "{app}\PAP-Editor.exe"
Name: "{autodesktop}\PAP Editor"; Filename: "{app}\PAP-Editor.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Desktop-Verknüpfung erstellen"; GroupDescription: "Zusätzliche Symbole:"

[Run]
Filename: "{app}\PAP-Editor.exe"; Description: "PAP Editor starten"; Flags: nowait postinstall skipifsilent
