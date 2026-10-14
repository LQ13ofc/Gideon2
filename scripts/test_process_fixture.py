import subprocess,sys,unittest
from process_fixture import command_line,resident_bytes
class Tests(unittest.TestCase):
    def test_exited_owned_process_does_not_fail_sampling(self):
        child=subprocess.Popen([sys.executable,'-c','pass']);child.wait(timeout=3)
        self.assertEqual(command_line(child.pid),b'')
    def test_rss_sampler_handles_live_and_exited_owned_children(self):
        child=subprocess.Popen([sys.executable,'-c',"import time; print('ready',flush=True); time.sleep(5)"],stdout=subprocess.PIPE)
        try:
            self.assertEqual(child.stdout.readline(),b'ready\n')
            self.assertGreater(resident_bytes(child.pid),0)
        finally:child.terminate();child.wait(timeout=3);child.stdout.close()
        self.assertEqual(resident_bytes(child.pid),0)
if __name__=='__main__':unittest.main()
