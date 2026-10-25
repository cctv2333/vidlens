Add-Type -AssemblyName System.Speech
$dir = 'D:\app\vidlens\demo'
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice('Microsoft Huihui Desktop')
$ssml = [IO.File]::ReadAllText((Join-Path $dir 'demo.ssml'), [Text.Encoding]::UTF8)
$s.SetOutputToWaveFile((Join-Path $dir 'speech.wav'))
$s.SpeakSsml($ssml)
$s.Dispose()
$f = Get-Item (Join-Path $dir 'speech.wav')
"wav bytes: $($f.Length)"

$ff = 'D:\app\vidlens\.venv\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe'
$colors = @('0x1e3a5f', '0x7a2e2e', '0x2e5f3a', '0x8a8a8a')
$durs = @(8, 8, 8, 6)
$a = @()
for ($i = 0; $i -lt 4; $i++) { $a += @('-f', 'lavfi', '-i', "color=c=$($colors[$i]):s=1280x720:d=$($durs[$i]):r=25") }
$a += @('-i', (Join-Path $dir 'speech.wav'))
$filter = '[0:v][1:v][2:v][3:v]concat=n=4:v=1:a=0,fps=25[v]'
$a += @('-filter_complex', $filter, '-map', '[v]', '-map', '4:a',
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '23', '-c:a', 'aac', '-b:a', '128k',
    '-t', '30', '-af', 'apad', '-shortest', '-y', (Join-Path $dir 'meeting.mp4'))
& $ff @a 2>&1 | Select-Object -Last 4
$v = Get-Item (Join-Path $dir 'meeting.mp4')
"mp4 bytes: $($v.Length)"
