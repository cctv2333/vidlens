import subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, r"D:\vidlens\vidlens")
import vidlens_web as web
td = tempfile.mkdtemp()
child = "import sys,time; sys.path.insert(0,r'D:\\vidlens\\vidlens'); from vidlens_web import media_lock; from pathlib import Path; lk=media_lock(Path(sys.argv[1]),timeout=15); lk.__enter__(); print('locked',flush=True); time.sleep(4)"
p = subprocess.Popen([sys.executable, "-c", child, td], stdout=subprocess.PIPE, text=True)
print("child:", p.stdout.readline().strip())
lock = web.media_lock(Path(td), timeout=1.2)
t0=time.time()
try:
    with lock:
        print("PARENT ACQUIRED after %.2fs (no exclusion)" % (time.time()-t0))
except TimeoutError as e:
    print("parent blocked as expected after %.2fs: %s" % (time.time()-t0, e))
p.wait()
