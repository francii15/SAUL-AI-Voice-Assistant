Option Explicit
Dim files, runner, launcher, quote
Set files = CreateObject("Scripting.FileSystemObject")
Set runner = CreateObject("WScript.Shell")
launcher = files.BuildPath(files.GetParentFolderName(WScript.ScriptFullName), "Start_Saul_Floating.cmd")
quote = Chr(34)
If Not files.FileExists(launcher) Then
    MsgBox "Saul launcher was not found. Reinstall Saul in its original folder.", vbExclamation, "Saul"
    WScript.Quit 1
End If
runner.CurrentDirectory = files.GetParentFolderName(launcher)
runner.Run "cmd.exe /d /c " & quote & quote & launcher & quote & quote, 0, False
