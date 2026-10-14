"""Private Qt offscreen namespace shared by real Core integration checks."""
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]

def offscreen_command(root,artifacts,phase):
    python=BASE/'target/ui-venv/bin/python';runtime=python.resolve().parents[1];alias=python.readlink().parents[1]
    return ['/usr/bin/bwrap','--unshare-all','--die-with-parent','--ro-bind','/usr','/usr','--symlink','usr/lib','/lib','--symlink','usr/lib','/lib64','--ro-bind','/etc/fonts','/etc/fonts','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--ro-bind',str(runtime),str(runtime),'--ro-bind',str(runtime),str(alias),'--ro-bind',str(BASE),str(BASE),'--bind',str(root.parent),str(root.parent),'--setenv','HOME','/tmp','--setenv','XDG_CACHE_HOME','/tmp/cache','--setenv','XDG_CONFIG_HOME','/tmp/config','--setenv','XDG_RUNTIME_DIR','/tmp/runtime','--setenv','QT_QPA_PLATFORM','offscreen','--setenv','QT_QUICK_BACKEND','software','--setenv','QT_SCALE_FACTOR','2','--chdir','/tmp','--',str(python),'-I',str(BASE/'scripts/test_ui_offscreen.py'),'--root',str(root),'--artifacts',str(artifacts),'--phase',phase]
