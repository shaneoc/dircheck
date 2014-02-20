#!/usr/bin/python3

import sys
import os
import argparse
import subprocess
import stat
import csv
import datetime

csv_fieldorder = [
    'filename',
    'type',
    'mtime',
    'link',
    'size',
    'md5',
    'sha256'
]

csv_fieldnames = {
    'filename': 'filename',
    'type':     'type',
    'mtime':    'mtime',
    'link':     'symbolic link target',
    'size':     'size (bytes)',
    'md5':      'md5 sum',
    'sha256':   'sha256 sum'
}

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
        relfilename = os.path.relpath(filename, start=self.data_dir)
        
        if   stat.S_ISDIR(s.st_mode):  type = 'dir'
        elif stat.S_ISCHR(s.st_mode):  type = 'chr'
        elif stat.S_ISBLK(s.st_mode):  type = 'blk'
        elif stat.S_ISREG(s.st_mode):  type = 'file'
        elif stat.S_ISFIFO(s.st_mode): type = 'fifo'
        elif stat.S_ISLNK(s.st_mode):  type = 'lnk'
        elif stat.S_ISSOCK(s.st_mode): type = 'sock'
        else: sys.exit('Error: file {} is of unknown type'.format(filename))
        
        link_target = os.readlink(filename)              if type == 'lnk'  else ''
        md5sum      = self.hash_file(filename, 'md5')    if type == 'file' else ''
        sha256sum   = self.hash_file(filename, 'sha256') if type == 'file' else ''
        
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
        hashsum_bin = '/usr/bin/{}sum'.format(hash_type)
        try:
            output = subprocess.check_output(
                [hashsum_bin, '-b', filename],
                universal_newlines=True)
            return output.split()[0]
        except subprocess.CalledProcessError as e:
            sys.exit('Error: failed hashing file {} (return code: {})'.format(
                filename, e.returncode))
    
    def hash_action(self):
        # TODO implement ability to update hashes without the possibly
        #      of unnoticed data corruption while updating
        with open(self.csv_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, csv_fieldorder)
            writer.writerow(csv_fieldnames)
            for fileinfo in self.scan_db:
                writer.writerow(fileinfo)
    
    def check_action(self):
        print(' * Comparing to hash file...')
        if not os.path.isfile(self.csv_file):
            sys.exit('Error: hash file either does exist or is not a file: ' + \
                self.csv_file)
        
        with open(self.csv_file, newline='') as f:
            # TODO maybe change this to obey the header line in the CSV?
            reader = csv.DictReader(f, csv_fieldorder, restval='')
            first = True
            csv_db = []
            for row in reader:
                if first: first = False
                else: csv_db.append(row)
            csv_db.sort(key = lambda x: x['filename'])
        
        error_occured = False
        def stderr(msg):
            nonlocal error_occured
            print(msg, file=sys.stderr)
            error_occured = True
        
        scan_idx = csv_idx = 0
        while scan_idx < len(self.scan_db) or csv_idx < len(csv_db):
            scan_file = self.scan_db[scan_idx] if scan_idx < len(self.scan_db) else None
            csv_file  = csv_db[csv_idx] if csv_idx < len(csv_db) else None
            
            if scan_file == csv_file:
                scan_idx += 1
                csv_idx  += 1
                continue
            
            if csv_file == None or scan_file['filename'] < csv_file['filename']:
                stderr('Mismatch: file is missing from the hash file: ' + \
                    scan_file['filename'])
                scan_idx += 1
                continue
            
            if scan_file == None or csv_file['filename'] < scan_file['filename']:
                stderr('Mismatch: file is missing from disk: ' + \
                    csv_file['filename'])
                csv_idx += 1
                continue
            
            stderr('Mismatch: file properties have changed: ' + \
                scan_file['filename'])
            for field in csv_fieldorder:
                if scan_file[field] != csv_file[field]:
                    def tstamp(val):
                        try:
                            return '{}.{:09} ({})'.format(
                                datetime.datetime.fromtimestamp(int(val) // (10**9)).isoformat(' '),
                                int(val) % (10**9), val)
                        except (ValueError, OSError):
                            return 'invalid timestamp ({})'.format(val)
                    
                    if csv_file[field] == '':  old_val = 'none'
                    elif field == 'mtime':     old_val = tstamp(csv_file[field])
                    else:                      old_val = csv_file[field]
                    
                    if scan_file[field] == '': new_val = 'none'
                    elif field == 'mtime':     new_val = tstamp(scan_file[field])
                    else:                      new_val = scan_file[field]
                    
                    stderr('  {}: {} changed to {}'.format(
                        csv_fieldnames[field], old_val, new_val))
            scan_idx += 1
            csv_idx  += 1
        
        if error_occured:
            sys.exit(1)
        else:
            print('Successfully compared {} files ({} bytes), no mismatches'.format(
                len(csv_db), sum(int(csv_file['size']) for csv_file in csv_db)))


if __name__ == '__main__':
    Main()
