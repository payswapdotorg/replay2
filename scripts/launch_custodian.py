import subprocess

# launcher pattern (REQUIRED for tool-shell-originated daemons): the bash
# tool kills its own descendants when the session ends — a child re-parented
# to init (via immediate launcher exit) survives. See worklog ring-of-three.
p = subprocess.Popen(["/home/z/.venv/bin/python3", "/home/z/my-project/scripts/custodian.py"],
    stdout=open("/home/z/my-project/scripts/logs/custodian.log", "a"),
    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
    start_new_session=True, cwd="/home/z/my-project/scripts")
open("/home/z/my-project/scripts/custodian.pid", "w").write(str(p.pid))
print("custodian pid", p.pid)
