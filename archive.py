#!/usr/bin/python3
import sys
import os
import subprocess
import argparse
import datetime

# valid years
all_years = [1992, 1996, 1998] + list(range(2000, datetime.date.today().year+1))

# parse arguments
parser = argparse.ArgumentParser()
parser.add_argument('action', choices=['hash', 'backup-full', 'backup-incr', 'backup-ls', 'check', 'check-old-hash'])
parser.add_argument('archive_dir', metavar='archive-dir')
parser.add_argument('year', nargs='+',
    type=lambda x: 'all' if x == 'all' else int(x),
    help='archive year to use (or "all" for all years)')
parser.add_argument('-d', '--debug', action='store_true',
    help='print commands to be run without running them')
args = parser.parse_args()

# helper functions
def call(cmd, *pargs, **kwargs):
    cmd = cmd.format(*pargs, **kwargs)
    print('$ ' + cmd)
    if args.debug:
        print('command not run due to debug mode')
    else:
        sys.stdout.flush()
        ret = subprocess.call(cmd, shell=True)
        if ret != 0:
            sys.exit('Error: command returned error code {}'.format(ret))

# determine paths
archive_dir = os.path.abspath(args.archive_dir)
if not os.path.isdir(archive_dir):
    sys.exit('Error: archive directory "{}" not found'.format(archive_dir))

passphrase_file     = os.path.join(archive_dir, 'passphrase.txt')
duplicity_cache_dir = os.path.join(archive_dir, 'duplicity-cache')

# determine years
years = all_years if any(year == 'all' for year in args.year) else args.year

# do action
for year in years:
    if year not in all_years:
        sys.exit('Error: archive year "{}" is invalid'.format(year))
    
    archive_year_dir = os.path.join(archive_dir, str(year))
    backup_year_dir  = os.path.join(archive_dir, 'backup', str(year))
    backup_hash_file = os.path.join(archive_dir, 'backup', '{}-backup-hashdeep.txt'.format(year))
    hashdeep_file    = os.path.join(archive_dir, 'hash', '{}-hashdeep.txt'.format(year))
    stat_file        = os.path.join(archive_dir, 'hash', '{}-stat.csv'.format(year))
    hash_file_glob   = os.path.join(archive_dir, 'hash', '{}-*'.format(year))
    stat_cmd         = 'find "{}" -print0 | sort -z | xargs -0 '.format(archive_year_dir) + \
        'stat -c "%N,%F,%s,%f,%a,%A,%U,%G,%w (%W),%y (%Y),%z (%Z)"'
    include_args     = '--include "{}" --include "{}" --exclude "/**"'.format(
        archive_year_dir, hash_file_glob)
    duplicity_args   = '--name "archive-{}" --archive-dir "{}"'.format(year, duplicity_cache_dir)
    
    if not os.path.isdir(archive_year_dir):
        sys.exit('Error: archive year "{}" not found'.format(archive_year_dir))
    
    if args.action == 'hash':
        if os.path.exists(hashdeep_file):
            call('mv "{}" "{}"', hashdeep_file, hashdeep_file + '.old')
        call('hashdeep -r "{}" > "{}"', archive_year_dir, hashdeep_file)
        if os.path.exists(stat_file):
            call('mv "{}" "{}"', stat_file, stat_file + '.old')
        call('{} > "{}"', stat_cmd, stat_file)
        print('-'*80)
        print('NOTE: The hash for {} has been updated. You should now run check-old-hash'.format(year))
        print('      to ensure that an additional file corruption has not occured while')
        print('      updating the hash.')
        print('-'*80)
    
    if args.action == 'check-old-hash':
        if os.path.getsize(hashdeep_file + '.old') == 0:
            call('test ! "$(ls -A "{}")"', archive_year_dir)
        else:
            call('hashdeep -r -a -vv -k "{}" "{}"', hashdeep_file + '.old', archive_year_dir)
        call('{} | diff "{}" -', stat_cmd, stat_file + '.old')
    
    if args.action == 'check':
        if os.path.getsize(hashdeep_file) == 0:
            call('test ! "$(ls -A "{}")"', archive_year_dir)
        else:
            call('hashdeep -r -a -vv -k "{}" "{}"', hashdeep_file, archive_year_dir)
        call('{} | diff "{}" -', stat_cmd, stat_file)
        
        call('hashdeep -r -a -vv -k "{}" "{}"', backup_hash_file, backup_year_dir)
        os.environ['PASSPHRASE'] = open(passphrase_file).read()
        call('duplicity verify {} {} "file://{}" "{}"', duplicity_args,
             include_args, backup_year_dir, archive_dir)
        call('duplicity collection-status {} "file://{}"', duplicity_args, backup_year_dir)
    
    if args.action in ('backup-full', 'backup-incr'):
        os.environ['PASSPHRASE'] = open(passphrase_file).read()
        duplicity_action = 'full' if args.action == 'backup-full' else 'incr'
        call('duplicity {} {} {} "{}" "file://{}"', duplicity_action,
            duplicity_args, include_args, archive_dir, backup_year_dir)
        call('hashdeep -r "{}" > "{}"', backup_year_dir, backup_hash_file)
    
    if args.action == 'backup-ls':
        os.environ['PASSPHRASE'] = open(passphrase_file).read()
        call('duplicity list-current-files {} "file://{}"', duplicity_args, backup_year_dir)
        
    
