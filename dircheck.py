#!/usr/bin/python3

import sys
import os
import argparse
import subprocess
import stat
import csv
import datetime
import io
import hashlib

csv_fieldnames = [
    'filename',
    'type',
    'mtime',
    'link',
    'size',
    'md5',
    'sha256'
]

csv_humanfieldnames = {
    'filename': 'filename',
    'type':     'type',
    'mtime':    'mtime',
    'link':     'symbolic link target',
    'size':     'size (bytes)',
    'md5':      'md5 sum',
    'sha256':   'sha256 sum'
}

# preallocate a single buffer for hashing, for speed
hashbuf     = bytearray(1048576) # 1 MB
hashbufview = memoryview(hashbuf)

class Main:
    def __init__(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('action', choices=['hash', 'check'])
        parser.add_argument('data_dir', metavar='DIR',
            help='the directory of files to hash or check')
        parser.add_argument('-f', '--hash-file', metavar='FILE',
            help='the file to use to store hashes for this directory')
        args = parser.parse_args()
        
        self.data_dir = args.data_dir
        self.csv_file = args.hash_file if args.hash_file else \
            os.path.join(self.data_dir, 'dircheck.csv')

        if not os.path.isdir(self.data_dir):
            sys.exit('Error: "{}" is not a directory'.format(self.data_dir))
        
        print('Directory: ' + self.data_dir)
        print('Hash file: ' + self.csv_file)
        
        self.scan_data_size = 0
        self.scan_db = []
        print(' * Scanning...')
        self.scan_dir(self.data_dir)
        self.scan_db.sort(key = lambda x: x['filename'])
        
        if args.action == 'hash':
            self.hash_action()
        else:
            self.check_action()

    def scan_dir(self, dirpath):
        for filename in os.listdir(dirpath):
            filepath = os.path.join(dirpath, filename)
            if os.path.abspath(self.csv_file) == \
                    os.path.abspath(filepath):
                continue
            
            fileinfo = self.scan_file(filepath)
            self.scan_db.append(fileinfo)
            if fileinfo['type'] == 'dir':
                self.scan_dir(filepath)

    def scan_file(self, filename):
        s = os.lstat(filename)
        if   stat.S_ISDIR(s.st_mode):  type = 'dir'
        elif stat.S_ISCHR(s.st_mode):  type = 'chr'
        elif stat.S_ISBLK(s.st_mode):  type = 'blk'
        elif stat.S_ISREG(s.st_mode):  type = 'file'
        elif stat.S_ISFIFO(s.st_mode): type = 'fifo'
        elif stat.S_ISLNK(s.st_mode):  type = 'lnk'
        elif stat.S_ISSOCK(s.st_mode): type = 'sock'
        else: sys.exit('Error: file {} is of unknown type'.format(filename))
        
        relfilename = os.path.relpath(filename, start=self.data_dir)
        if type == 'dir': relfilename += '/' # it looks nicer this way!
        link_target = os.readlink(filename)              if type == 'lnk'  else ''
        md5sum      = self.hash_file(filename, 'md5')    if type == 'file' else ''
        sha256sum   = self.hash_file(filename, 'sha256') if type == 'file' else ''
        
        self.scan_data_size += s.st_size
        
        return {'filename': relfilename,
                'type':     type,
                # TODO should I save these other things?
                #'mode':     oct(stat.S_IMODE(s.st_mode)),
                #'uid':      str(s.st_uid),
                #'gid':      str(s.st_gid),
                'mtime':    str(s.st_mtime_ns),
                #'ctime':    str(s.st_ctime_ns),
                'link':     link_target,
                'size':     str(s.st_size),
                'md5':      md5sum,
                'sha256':   sha256sum}
    
    def hash_file(self, filename, hash_type):
        assert hash_type in ('md5', 'sha256')
        h = hashlib.md5() if hash_type == 'md5' else hashlib.sha256()
        
        with open(filename, 'rb', buffering=0) as f:
            while True:
                size = f.readinto(hashbuf)
                if size == 0: break
                h.update(hashbufview[:size])
        return h.hexdigest()
    
    def hash_action(self):
        if os.path.exists(self.csv_file):
            msgs = [' * Mismatches from existing hash file found:\n' + ('-'*80) + '\n']
            # TODO send messages to less as they happen rather than
            #      buffer them up first
            #      https://gist.github.com/waylan/2353749
            def msgfunc(msg):
                msgs.append(msg + '\n')
            self.compare_csv(msgfunc)
        
            if len(msgs) > 1:
                p = subprocess.Popen(['/usr/bin/less', '-S'], stdin=subprocess.PIPE, universal_newlines=True)
                p.communicate(''.join(msgs))
                if input(' * Accept hash changes and update? [y/N] ') != 'y':
                    sys.exit()
            else:
                print(' * No changes detected from previous hash file!')
            
            print(' * Generating new hash file...')
        else:
            print(' * Generating hash file...')
        
        with open(self.csv_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, csv_fieldnames)
            writer.writerow({field: field for field in csv_fieldnames})
            for fileinfo in self.scan_db:
                writer.writerow(fileinfo)
        
        print(' * Successfully hashed {} files ({} bytes)'.format(
            len(self.scan_db), self.scan_data_size))
    
    def check_action(self):
        error_occured = False
        def msgfunc(msg):
            nonlocal error_occured
            error_occured = True
            print(msg) # TODO should this be stderr??
        
        self.compare_csv(msgfunc)
        
        if error_occured:
            sys.exit(1)
        else:
            print(' * Successfully compared {} files ({} bytes), no mismatches'.format(
                len(self.scan_db), self.scan_data_size))
        
        
    def compare_csv(self, msgfunc):
        print(' * Comparing to hash file...')
        if not os.path.isfile(self.csv_file):
            sys.exit('Error: hash file either does exist or is not a file: ' + \
                self.csv_file)
        
        with open(self.csv_file, newline='') as f:
            reader = csv.DictReader(f, restval='')
            if 'filename' not in reader.fieldnames:
                sys.exit('Error: hash file is missing a filename field')
            csv_db = [row for row in reader]
            csv_db.sort(key = lambda x: x['filename'])
        
        scan_idx = csv_idx = 0
        while scan_idx < len(self.scan_db) or csv_idx < len(csv_db):
            scan_file = self.scan_db[scan_idx] if scan_idx < len(self.scan_db) else None
            csv_file = csv_db[csv_idx] if csv_idx < len(csv_db) else None
            prev_csv_file = csv_db[csv_idx-1] if csv_idx >= 1 and csv_idx < len(csv_db) else None
            
            if scan_file == csv_file:
                scan_idx += 1
                csv_idx  += 1
                continue
            
            if csv_file != None:
                if prev_csv_file != None and csv_file['filename'] == prev_csv_file['filename']:
                    sys.exit('Error: hash file has duplicate entries for file: ' + csv_file['filename'])
            
                if scan_file == None or csv_file['filename'] < scan_file['filename']:
                    msgfunc('Mismatch: file is missing from disk: ' + \
                        csv_file['filename'])
                    csv_idx += 1
                    continue
            
            if scan_file != None:
                if csv_file == None or scan_file['filename'] < csv_file['filename']:
                    msgfunc('Mismatch: file is missing from the hash file: ' + \
                        scan_file['filename'])
                    scan_idx += 1
                    continue
            
            msgfunc('Mismatch: file properties have changed: ' + \
                scan_file['filename'])
            for field in scan_file:
                scan_val = scan_file.get(field, '')
                csv_val = csv_file.get(field, '')
                if scan_val != csv_val:
                    def tstamp(val):
                        try:
                            return '{}.{:09} ({})'.format(
                                datetime.datetime.fromtimestamp(int(val) // (10**9)).isoformat(' '),
                                int(val) % (10**9), val)
                        except (ValueError, OSError):
                            return 'invalid timestamp ({})'.format(val)
                    
                    if csv_val == '':      old_val = 'none'
                    elif field == 'mtime': old_val = tstamp(csv_val)
                    else:                  old_val = csv_val
                    
                    if scan_val == '':     new_val = 'none'
                    elif field == 'mtime': new_val = tstamp(scan_val)
                    else:                  new_val = scan_val
                    
                    msgfunc('  {}: {} changed to {}'.format(
                        csv_humanfieldnames[field], old_val, new_val))
            scan_idx += 1
            csv_idx  += 1


if __name__ == '__main__':
    Main()
