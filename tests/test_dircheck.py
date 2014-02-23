from dircheck import dircheck
import sys
import os
import unittest
import tempfile
import shutil

test_dir = 'test-dir-123123'

class TestDircheck(unittest.TestCase):
    def runDircheck(self, *args):
        sys.argv = ['dircheck'] + list(args)
        dircheck.Main()
        
    def assertSysExits(self, *args):
        with self.assertRaises(SystemExit) as cm:
            self.runDircheck(*args)
        self.assertEqual(cm.exception.code, 1)
        
    def setUp(self):
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
        os.mkdir(test_dir)
        os.chdir(test_dir)
        for i in range(10):
            os.system('echo {} > testfile-{}.txt'.format('%'*i*10, i))
            os.mkdir('testdir-{}'.format(i))
            os.system('echo test > testdir-{}/test.txt'.format(i))
        self.runDircheck('hash', '.')

    def test_no_cuange(self):
        self.runDircheck('check', '.')

    def test_new_file(self):
        os.system('touch test.txt')
        self.assertSysExits('check', '.')

    def test_change_file(self):
        os.system('echo testmore > testdir-0/test.txt')
        self.assertSysExits('check', '.')

    def test_change_file_2(self):
        os.system('rm testdir-2/test.txt')
        os.system('mkdir testdir-2/test.txt')
        self.assertSysExits('check', '.')

    def test_change_mtime(self):
        os.system('touch testfile-0.txt')
        self.assertSysExits('check', '.')

    def tearDown(self):
        os.chdir('..')
        shutil.rmtree(test_dir) 


if __name__ == '__main__':
    unittest.main()
