$env:PYTHONIOENCODING='utf-8'
$env:HF_HUB_DISABLE_XET='1'
$py = 'D:\vidlens\vidlens\.venv\Scripts\python.exe'
$vl = 'D:\vidlens\vidlens\vidlens.py'
$log = 'D:\vidlens\vidlens\out\run_three.log'
"START $(Get-Date -Format HH:mm:ss)" | Out-File $log -Encoding utf8

foreach ($u in @(
    'https://www.bilibili.com/video/BV17LHw64EMX/',
    'https://www.bilibili.com/video/BV1Kwnr61EeS/',
    'https://www.bilibili.com/video/BV1oUJB6QEL5/')) {
    "--- $u ---" | Out-File $log -Append -Encoding utf8
    & $py $vl grab $u --lang zh --model small *>> $log
}

"--- visual scan for the short film ---" | Out-File $log -Append -Encoding utf8
& $py $vl scan 'https://www.bilibili.com/video/BV1oUJB6QEL5/' --n 20 --cols 5 --rows 4 *>> $log

"ALL DONE" | Out-File $log -Append -Encoding utf8
