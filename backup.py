"""Offline backup/restore. Stop EduMind before running this script."""
import argparse
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
import os
from dotenv import load_dotenv

load_dotenv()
ROOT=Path(__file__).resolve().parent
DATA=Path(os.getenv('EDUMIND_DATA',str(ROOT/'data')))

def backup():
    if not (DATA/'edumind.db').is_file():
        raise ValueError('No database found. Start EduMind once before making a backup.')
    out=ROOT/'backups';out.mkdir(exist_ok=True)
    target=out/('EduMind-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.zip')
    # SQLite backup API produces a consistent DB snapshot; stop the app so uploaded files cannot change mid-backup.
    snapshot=out/'snapshot.sqlite'
    try:
        with sqlite3.connect(DATA/'edumind.db') as source, sqlite3.connect(snapshot) as dest:
            source.backup(dest)
        with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
            z.write(snapshot,'edumind.db')
            for f in (DATA/'uploads').glob('*'):
                if f.is_file() and not f.is_symlink(): z.write(f,'uploads/'+f.name)
    finally:
        snapshot.unlink(missing_ok=True)
    print('Private backup saved:',target)

def restore(source):
    if DATA.exists():
        raise ValueError('Refusing to overwrite an existing data directory. Move it somewhere safe first.')
    with zipfile.ZipFile(source) as z:
        infos=z.infolist()
        if sum(i.file_size for i in infos)>2*1024**3:
            raise ValueError('Archive exceeds the 2 GB restore limit.')
        if 'edumind.db' not in z.namelist(): raise ValueError('Archive is missing edumind.db.')
        for i in infos:
            p=PurePosixPath(i.filename)
            if '\\' in i.filename or ':' in i.filename or p.is_absolute() or '..' in p.parts or (p.parts[0]!='uploads' and i.filename!='edumind.db'):
                raise ValueError('Archive has an invalid member path.')
        DATA.mkdir(parents=True)
        for i in infos:
            dest=DATA.joinpath(*PurePosixPath(i.filename).parts)
            if i.is_dir(): dest.mkdir(parents=True,exist_ok=True)
            else:
                dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(z.read(i))
        (DATA/'uploads').mkdir(exist_ok=True)
    print('Restored data to:',DATA)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore',type=Path)
    args=parser.parse_args()
    try:
        if args.restore: restore(args.restore)
        else: backup()
    except (ValueError,OSError,zipfile.BadZipFile) as exc:
        parser.exit(1,str(exc)+'\n')
