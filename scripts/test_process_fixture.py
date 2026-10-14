import subprocess,sys,unittest
from process_fixture import command_line
class Tests(unittest.TestCase):
    def test_exited_owned_process_does_not_fail_sampling(self):
        child=subprocess.Popen([sys.executable,'-c','pass']);child.wait(timeout=3)
        self.assertEqual(command_line(child.pid),b'')
if __name__=='__main__':unittest.main()
