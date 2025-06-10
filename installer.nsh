!include "MUI2.nsh"

; General
Name "Junior Desktop"
OutFile "dist/Junior-Setup.exe"
InstallDir "$LOCALAPPDATA\Junior"
InstallDirRegKey HKCU "Software\Junior" ""

; Request application privileges for Windows Vista and above
RequestExecutionLevel user

; UI Configuration
!define MUI_ICON "assets/icons/icon.ico"
!define MUI_ABORTWARNING

; Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_LANGUAGE "English"

; Installer sections
Section "Junior Desktop" SecMain
  SetOutPath "$INSTDIR"
  
  ; Add files
  File /r "dist\win-unpacked\*.*"
  
  ; Create start menu shortcut
  CreateDirectory "$SMPROGRAMS\Junior"
  CreateShortCut "$SMPROGRAMS\Junior\Junior.lnk" "$INSTDIR\Junior.exe"
  CreateShortCut "$DESKTOP\Junior.lnk" "$INSTDIR\Junior.exe"
  
  ; Write installation info
  WriteRegStr HKCU "Software\Junior" "" $INSTDIR
  WriteUninstaller "$INSTDIR\uninstall.exe"
  
  ; Add uninstaller to Add/Remove Programs
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Junior" \
               "DisplayName" "Junior Desktop"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Junior" \
               "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Junior" \
               "DisplayIcon" '"$INSTDIR\Junior.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Junior" \
               "Publisher" "Junior"
SectionEnd

; Uninstaller
Section "Uninstall"
  ; Remove files
  RMDir /r "$INSTDIR"
  
  ; Remove shortcuts
  Delete "$SMPROGRAMS\Junior\Junior.lnk"
  RMDir "$SMPROGRAMS\Junior"
  Delete "$DESKTOP\Junior.lnk"
  
  ; Remove registry keys
  DeleteRegKey HKCU "Software\Junior"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Junior"
SectionEnd
