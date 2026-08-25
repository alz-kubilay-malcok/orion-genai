Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in 8001,8501,3000,3001,8200 } |
    Select-Object LocalPort, OwningProcess |
    Format-Table -AutoSize
Get-Process -Name python -ErrorAction SilentlyContinue |
    Select-Object Id, StartTime, ProcessName,
        @{n='Cmd';e={(Get-CimInstance Win32_Process -Filter ("ProcessId="+$_.Id)).CommandLine}} |
    Format-Table -AutoSize -Wrap
