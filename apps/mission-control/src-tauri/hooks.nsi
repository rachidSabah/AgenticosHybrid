; AgenticOS NSIS custom installer hooks
; Ensures WebView2Loader.dll is placed BESIDE agentic-os.exe in $INSTDIR.
; Windows DLL search order requires the DLL to be in the EXE's own directory.

!macro customInstall
  ; WebView2Loader.dll must be in $INSTDIR (same folder as agentic-os.exe).
  ; The Tauri bundler places it in $INSTDIR\resources\ — copy it up one level.
  IfFileExists "$INSTDIR\resources\WebView2Loader.dll" 0 already_at_root
    CopyFiles /SILENT "$INSTDIR\resources\WebView2Loader.dll" "$INSTDIR\WebView2Loader.dll"
  already_at_root:
!macroend

!macro customUninstall
  Delete "$INSTDIR\WebView2Loader.dll"
!macroend
