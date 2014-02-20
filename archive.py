#!/usr/bin/python3
import sys
import os
import subprocess
import argparse
import datetime

class Config:
    def __init__(self, actions):
        # parse arguments
        parser = argparse.ArgumentParser()
        parser.add_argument('action', choices=actions)
            #'backup-full', 'backup-incr', 'backup-ls',
            #'hash', 'check', 'check-old-hash', 'sync'])
        parser.add_argument('year', nargs='+',
            type=lambda x: 'all' if x == 'all' else int(x),
            help='archive year to use (or "all" for all years)')
        parser.add_argument('-a', '--archive-dir', metavar='DIR', default=os.getcwd(),
            help='the directory containing the archive (defaults to the current directory)')
        parser.add_argument('-d', '--debug', action='store_true',
            help='print commands to be run without running them')
        args = parser.parse_args()
        
        self.action = args.action
        self.debug  = args.debug
        
        # determine years
        all_years = [1992, 1996, 1998] + list(range(2000, datetime.date.today().year+1))
        years = all_years if any(year == 'all' for year in args.year) else args.year
        if any(year not in all_years for year in years):
            sys.exit('Error: invalid year')
        
        # determine paths
        self.archive_dir = os.path.abspath(args.archive_dir)
        
        # TODO check permissions on everything
        join = os.path.join
        self.backup_dir          = join(self.archive_dir, 'backup')
        self.duplicity_cache_dir = join(self.archive_dir, 'cache')
        self.passphrase_file     = join(self.archive_dir, 'passphrase.txt')
        self.s3_config_file      = join(self.archive_dir, 's3cfg.txt')
        self.s3_bucket_file      = join(self.archive_dir, 's3bucket.txt')
        
        for d in (self.archive_dir, self.backup_dir):
            if not os.path.isdir(d):
                sys.exit('Error: directory "{}" does not exist or is not a directory'.format(d))
        
        for f in (self.passphrase_file, self.s3_config_file, self.s3_bucket_file):
            if not os.path.isfile(f):
                sys.exit('Error: file "{}" does not exist or is not a file'.format(f))
        
        self.passphrase = open(self.passphrase_file).read().strip()
        self.s3_bucket  = open(self.s3_bucket_file).read().strip()
        
        class YearConfig:
            def __init__(self, cfg, year):
                self.year           = year
                self.archive_dir    = join(cfg.archive_dir, str(year))
                self.backup_dir     = join(cfg.backup_dir,  str(year))
                self.duplicity_args = '--name "archive-{}" --archive-dir "{}"'.format(
                    year, cfg.duplicity_cache_dir)
                
                if not os.path.isdir(self.archive_dir):
                    sys.exit('Error: directory "{}" does not exist'.format(self.archive_dir))
        
        self.years = {year: YearConfig(self, year) for year in years}

class Main:
    def __init__(self):
        self.error_occured = False
        self.gcfg = Config(actions =
            sorted(attr[:-7].replace('_','-') for attr in dir(self) if attr[-7:] == '_action'))
        
        for year in sorted(self.gcfg.years.keys()):
            self.ycfg = self.gcfg.years[year]
            getattr(self, self.gcfg.action + '_action')()
            self._exiterror()
    
    def _call(self, cmd, *pargs, **kwargs):
        cmd = cmd.format(*pargs, **kwargs)
        #self.output += '$ {}\n'.format(cmd)
        print('$ ' + cmd)
        if self.gcfg.debug:
            #self.output += 'command not run due to debug mode\n'
            print('command not run due to debug mode\n')
        else:
            sys.stdout.flush()
            ret = subprocess.call(cmd, shell=True)
            if ret != 0:
                print('Error: command returned error code {}'.format(ret), file=sys.stderr)
                if 'exit_on_error' in kwargs and kwargs['exit_on_error']:
                    sys.exit(1)
                else:
                    self.error_occured = True
            #try:
            #    self.output += subprocess.check_output(cmd, universal_newlines=True,
            #        stderr=subprocess.STDOUT, shell=True).rtrim() + '\n'
            #except subprocess.CalledProcessError as e:
            #    self.output += e.output.rtrim() + '\n'
            #    self.output += 'Error: command returned error code {}'.format(e.returncode)
            #    self.error = True
    
    def _exitcall(self, cmd, *pargs, **kwargs):
        kwargs['exit_on_error'] = True
        self._call(cmd, *pargs, **kwargs)
    
    def _exiterror(self):
        if self.error_occured:
            sys.exit('Error: exiting due to previous error')
    
    def hash_action(self):
        self._exitcall('dircheck.py hash "{}"', self.ycfg.archive_dir)
    
    def check_hash_action(self):
        self._call('dircheck.py check "{}"', self.ycfg.archive_dir)
    
    def backup_full_action(self):
        self._backup('full')
    
    def backup_incr_action(self):
        self._backup('incr')
    
    def _backup(self, backup_type):
        assert backup_type in ('full', 'incr')
        os.environ['PASSPHRASE'] = self.gcfg.passphrase
        self._exitcall('duplicity {} {} "{}" "file://{}"', backup_type,
            self.ycfg.duplicity_args, self.ycfg.archive_dir, self.ycfg.backup_dir)
        os.environ['PASSPHRASE'] = ''
        
        # TODO hash the backup with dircheck.py
    
    def backup_ls_action(self):
        os.environ['PASSPHRASE'] = self.gcfg.passphrase
        self._exitcall('duplicity list-current-files {} "file://{}"',
            self.ycfg.duplicity_args, self.ycfg.archive_dir)
        os.environ['PASSPHRASE'] = ''
    
    def check_backup_action(self):
        os.environ['PASSPHRASE'] = self.gcfg.passphrase
        self._call('duplicity verify {} "file://{}" "{}"',
            self.ycfg.duplicity_args, self.ycfg.backup_dir, self.ycfg.archive_dir)
        #cmd.call('duplicity collection-status {} "file://{}"', duplicity_args, backup_year_dir)
        os.environ['PASSPHRASE'] = ''
    
    def sync_action(self):
        self._exitcall('s3cmd -c "{}" sync --delete-removed --acl-private "{}/" "s3://{}/backup/{}/"',
            self.gcfg.s3_config_file, self.ycfg.backup_dir, self.gcfg.s3_bucket, self.ycfg.year)
    
    def check_sync_action(self):
        self._exitcall('out=$(s3cmd -c "{}" sync --dry-run --delete-removed --acl-private "{}/" "s3://{}/backup/{}/"); echo "$out"; test $(echo "$out" | wc -l) -eq 1',
            self.gcfg.s3_config_file, self.ycfg.backup_dir, self.gcfg.s3_bucket, self.ycfg.year)
        
    def check_action(self):
        self.check_hash_action()
        self.check_backup_action()
        self.check_sync_action()

if __name__ == '__main__':
    Main()
