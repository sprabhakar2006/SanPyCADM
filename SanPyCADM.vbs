' SanPyCADM.vbs -- double-click launcher for Windows, no
' command line needed. This is the B-rep-first copy of SanPyCAD, built
' on build123d/OpenCASCADE instead of triangle meshes; every label here
' says "SanPyCADM" specifically so it's never confused with the
' other two SanPyCAD folders when installed side by side.
'
' This is the Windows equivalent of SanPyCADM.app on macOS:
' it finds a Python 3 interpreter that actually has the packages this app
' needs (numpy, build123d), then runs app.py with no console window
' popping up (the app's own window, opened by pywebview, still appears
' normally -- only the Python interpreter's own console is hidden). If
' something goes wrong, it shows a message box instead of failing
' silently, and always logs details to SanPyCADM.log next to this
' file, the same idea as the macOS launcher's log.
'
' Just double-click this file. Don't move it out of the project folder
' (it finds app.py relative to its own location, so the app still works
' if the whole folder is renamed or moved, as long as this file stays
' alongside app.py).

Option Explicit

Dim fso, shell, scriptDir, logPath, appPath
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
logPath = fso.BuildPath(scriptDir, "SanPyCADM.log")
appPath = fso.BuildPath(scriptDir, "app.py")

Sub LogLine(msg)
    Dim f
    Set f = fso.OpenTextFile(logPath, 8, True) ' 8 = ForAppending, True = create if missing
    f.WriteLine Now & "  " & msg
    f.Close
End Sub

Sub Alert(msg)
    MsgBox msg, vbExclamation, "SanPyCADM"
End Sub

' Wraps a candidate python command for safe use inside a "cmd /c ..."
' line: a bare launcher token like "py -3" or "python" is left alone
' (quoting it would make cmd look for a program literally named
' "py -3"), but an actual file path (which may contain spaces, e.g.
' "C:\Program Files\...") gets wrapped in quotes.
Function QuoteIfPath(cand)
    If InStr(cand, "\") > 0 Then
        QuoteIfPath = """" & cand & """"
    Else
        QuoteIfPath = cand
    End If
End Function

' The quiet ("no console window at all") equivalent of a candidate that
' worked: `py`'s own sibling launcher is `pyw`, and a plain python.exe's
' sibling is pythonw.exe in the same folder -- swap to that when it's
' available. Bare "python"/"python3" (no obvious "w" sibling to guess at)
' fall back to running as-is; the hidden window style used below still
' keeps its console from appearing.
Function QuietLauncher(cand)
    Dim lc, pw
    lc = LCase(Trim(cand))
    If lc = "py -3" Then
        QuietLauncher = "pyw -3"
    ElseIf lc = "py" Then
        QuietLauncher = "pyw"
    ElseIf InStr(cand, "\python.exe") > 0 Then
        pw = Replace(cand, "\python.exe", "\pythonw.exe")
        If fso.FileExists(pw) Then
            QuietLauncher = pw
        Else
            QuietLauncher = cand
        End If
    Else
        QuietLauncher = cand
    End If
End Function

If Not fso.FileExists(appPath) Then
    Alert "Could not find app.py next to SanPyCADM.vbs." & vbCrLf & _
          "Don't move this file out of the project folder."
    WScript.Quit 1
End If

LogLine "===== launch ====="

' Candidates roughly in order of how likely each is to be "the" Python
' the required packages were actually installed into. `py -3` is the
' official python.org launcher (version-aware, present on PATH by
' default on any python.org install) so it's tried first; the rest are
' fallbacks for setups where that launcher isn't registered.
Dim candidates, i, cand, cmd, tmpOut, rc, foundExe, found, errText, tf
candidates = Array( _
    "py -3", "py", "python", "python3", _
    shell.ExpandEnvironmentStrings("%LocalAppData%\Programs\Python\Python313\python.exe"), _
    shell.ExpandEnvironmentStrings("%LocalAppData%\Programs\Python\Python312\python.exe"), _
    shell.ExpandEnvironmentStrings("%LocalAppData%\Programs\Python\Python311\python.exe"), _
    shell.ExpandEnvironmentStrings("%LocalAppData%\Programs\Python\Python310\python.exe"), _
    shell.ExpandEnvironmentStrings("%LocalAppData%\Programs\Python\Python39\python.exe"), _
    "C:\Python313\python.exe", "C:\Python312\python.exe", _
    "C:\Python311\python.exe", "C:\Python310\python.exe", "C:\Python39\python.exe", _
    shell.ExpandEnvironmentStrings("%ProgramFiles%\Python313\python.exe"), _
    shell.ExpandEnvironmentStrings("%ProgramFiles%\Python312\python.exe"), _
    shell.ExpandEnvironmentStrings("%ProgramFiles%\Python311\python.exe") _
)

found = False
tmpOut = fso.BuildPath(shell.ExpandEnvironmentStrings("%TEMP%"), "sanpycad_check.txt")

For i = 0 To UBound(candidates)
    cand = candidates(i)
    If Len(cand) > 0 Then
        cmd = "cmd /c " & QuoteIfPath(cand) & _
              " -c ""import numpy, build123d"" > """ & tmpOut & """ 2>&1"
        rc = shell.Run(cmd, 0, True)
        If rc = 0 Then
            LogLine "OK: " & cand & " has numpy/build123d"
            foundExe = cand
            found = True
            Exit For
        Else
            errText = ""
            If fso.FileExists(tmpOut) Then
                Set tf = fso.OpenTextFile(tmpOut, 1)
                If Not tf.AtEndOfStream Then errText = tf.ReadLine
                tf.Close
            End If
            LogLine "skip: " & cand & " -- " & errText
        End If
    End If
Next

If fso.FileExists(tmpOut) Then fso.DeleteFile(tmpOut, True)

If Not found Then
    Alert "SanPyCADM couldn't find a Python 3 with numpy/build123d " & _
          "installed." & vbCrLf & "See SanPyCADM.log in this folder for what was tried." & _
          vbCrLf & vbCrLf & "Fix: open Command Prompt and run:" & vbCrLf & _
          "    pip install numpy build123d pywebview"
    WScript.Quit 42
End If

LogLine "Using: " & foundExe

Dim quietCmd, runCmd
quietCmd = QuietLauncher(foundExe)
LogLine "Launching with: " & quietCmd

runCmd = "cmd /c cd /d " & QuoteIfPath(scriptDir) & " && " & _
          QuoteIfPath(quietCmd) & " app.py >> " & QuoteIfPath(logPath) & " 2>&1"

' Wait (True) for app.py to actually exit -- same idea as the macOS
' launcher, which runs app.py in the foreground of its own wrapper
' script: it lets us tell the difference between "the window was closed
' normally" and "it crashed on startup", and show an alert for the
' latter. This still shows no console window (style 0 = hidden) --
' pywebview's own app window isn't affected, since that's a separate
' window pywebview itself creates once it's running.
rc = shell.Run(runCmd, 0, True)
If rc <> 0 Then
    Alert "SanPyCADM stopped unexpectedly (exit code " & rc & ")." & vbCrLf & _
          "See SanPyCADM.log in this folder for details."
End If
