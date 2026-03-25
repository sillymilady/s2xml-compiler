Unicode True

!define APP_NAME      "S2XML Compiler"
!define APP_VERSION   "1.0.0"
!define APP_PUBLISHER "S2XML Project"
!define INSTALL_DIR   "$PROGRAMFILES64\S2XML Compiler"
!define REG_KEY       "Software\Microsoft\Windows\CurrentVersion\Uninstall\S2XMLCompiler"

Name            "${APP_NAME}"
OutFile         "S2XML_Compiler_Setup.exe"
InstallDir      "${INSTALL_DIR}"
InstallDirRegKey HKLM "${REG_KEY}" "InstallLocation"
RequestExecutionLevel admin
SetCompressor    /SOLID lzma

!include "MUI2.nsh"
!include "LogicLib.nsh"

!define MUI_ABORTWARNING
!define MUI_ICON   "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"

!define MUI_WELCOMEPAGE_TITLE "Welcome to S2XML Compiler Setup"
!define MUI_WELCOMEPAGE_TEXT "S2XML Compiler lets you write Sims 2 mods as XML files and compile them into .package files.$\r$\n$\r$\nClick Next to continue."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES

!define MUI_FINISHPAGE_TITLE "Installation Complete!"
!define MUI_FINISHPAGE_TEXT "S2XML Compiler has been installed.$\r$\n$\r$\nShortcuts have been added to your Desktop and Start Menu."
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Launch S2XML Compiler"
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchApp
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

!insertmacro MUI_LANGUAGE "English"

Function .onInit
    ReadRegStr $R0 HKLM "${REG_KEY}" "UninstallString"
    StrCmp $R0 "" done
    MessageBox MB_YESNOCANCEL|MB_ICONQUESTION \
        "S2XML Compiler is already installed.$\r$\n$\r$\nClick Yes to uninstall it first, No to reinstall over it, or Cancel to quit." \
        IDYES uninstall IDNO done
    Abort
    uninstall:
        ReadRegStr $R1 HKLM "${REG_KEY}" "InstallLocation"
        ExecWait '"$R0" /S _?=$R1'
    done:
FunctionEnd

Section "S2XML Compiler"
    SectionIn RO
    SetOutPath "$INSTDIR"
    File "S2XML Compiler.exe"
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    WriteRegStr   HKLM "${REG_KEY}" "DisplayName"          "${APP_NAME}"
    WriteRegStr   HKLM "${REG_KEY}" "DisplayVersion"       "${APP_VERSION}"
    WriteRegStr   HKLM "${REG_KEY}" "Publisher"            "${APP_PUBLISHER}"
    WriteRegStr   HKLM "${REG_KEY}" "InstallLocation"      "$INSTDIR"
    WriteRegStr   HKLM "${REG_KEY}" "UninstallString"      '"$INSTDIR\Uninstall.exe"'
    WriteRegStr   HKLM "${REG_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
    WriteRegDWORD HKLM "${REG_KEY}" "NoModify"             1
    WriteRegDWORD HKLM "${REG_KEY}" "NoRepair"             1

    CreateShortcut "$DESKTOP\S2XML Compiler.lnk" \
        "$INSTDIR\S2XML Compiler.exe" "" \
        "$INSTDIR\S2XML Compiler.exe" 0 \
        SW_SHOWNORMAL "" "S2XML - Sims 2 Mod Compiler"

    CreateDirectory "$SMPROGRAMS\S2XML Compiler"
    CreateShortcut "$SMPROGRAMS\S2XML Compiler\S2XML Compiler.lnk" \
        "$INSTDIR\S2XML Compiler.exe" "" \
        "$INSTDIR\S2XML Compiler.exe" 0 \
        SW_SHOWNORMAL "" "S2XML - Sims 2 Mod Compiler"
    CreateShortcut "$SMPROGRAMS\S2XML Compiler\Uninstall.lnk" \
        "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
    Delete "$INSTDIR\S2XML Compiler.exe"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir  "$INSTDIR"
    Delete "$DESKTOP\S2XML Compiler.lnk"
    Delete "$SMPROGRAMS\S2XML Compiler\S2XML Compiler.lnk"
    Delete "$SMPROGRAMS\S2XML Compiler\Uninstall.lnk"
    RMDir  "$SMPROGRAMS\S2XML Compiler"
    DeleteRegKey HKLM "${REG_KEY}"
SectionEnd

Function LaunchApp
    Exec '"$INSTDIR\S2XML Compiler.exe"'
FunctionEnd
