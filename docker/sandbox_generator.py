#!/usr/bin/python3
import os
import yaml
import glob
import shutil
import re
import argparse
import boto3

try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper


def download_file(obj, file):
    s3 = boto3.client('s3')

    bucket = os.getenv('BUCKET_NAME')

    try: 
        with open(file, 'wb') as f:
            print(f"Downloading {obj} to {f} from bucket: {bucket}")
            s3.download_fileobj(bucket, obj, f)
    except Exception as e:
        raise(e)
    

with open('genconf.yml') as f:
    conf = yaml.load(f, Loader=Loader)

# Overwrite conf with env variable date/times
ibdate=os.getenv('IBDATE')
if ibdate:
    conf['IBDATE'] = ibdate

ibtime=os.getenv('IBTIME')
if ibtime:
    conf['IBTIME'] = ibtime

iedate=os.getenv('IEDATE')
if iedate:
    conf['IEDATE'] = iedate

ietime=os.getenv('IETIME')
if ietime:
    conf['IETIME'] = ietime

parser = argparse.ArgumentParser()
parser.add_argument(
    "--flexpart_dir", help="installation directory of flexpart", type=str)
parser.add_argument(
    "--sandbox_dir", help="directory where to generate the sandbox", type=str)
parser.add_argument(
    "--fdb", help="use fdb flag if using fdb instead of GRIB files as input", action='store_true')
parser.add_argument(
    "--s3", help="fetch data from S3 on AWS", action='store_true')
args = parser.parse_args()

conf['sandbox_dir'] = args.sandbox_dir
conf['flexpart_prefix'] = args.flexpart_dir

if args.fdb is True:
    conf['FDBFLAG'] = 1
else:
    conf['FDBFLAG'] = 0

os.makedirs(conf['sandbox_dir'], exist_ok=True)
os.symlink(conf['flexpart_prefix']+'/bin/FLEXPART',
           conf['sandbox_dir']+'/FLEXPART')

os.makedirs(conf['sandbox_dir']+'/grib', exist_ok=True)

for file in glob.glob(conf['data']):
    os.symlink(file, conf['sandbox_dir']+'/grib/'+os.path.basename(file))

os.makedirs(conf['sandbox_dir']+'/input', exist_ok=True)
shutil.copy(conf['flexpart_prefix']+'/share/options/AGECLASSES',
            conf['sandbox_dir']+'/input/AGECLASSES')

shutil.copy(conf['flexpart_prefix']+'/share/options/COMMAND',
            conf['sandbox_dir']+'/input/COMMAND')

with open(conf['flexpart_prefix']+'/share/options/COMMAND', 'r') as file:
    filedata = file.readlines()

# Generate COMMAND
outdata = []
for line in filedata:
    # Replace the target string

    for key in ['IBDATE', 'IEDATE']:
        line = re.sub(key+r'= *\d*, .*',
                      key+'={date},'.format(date=f"{conf[key]}"), line)

    for key in ['IBTIME', 'IETIME']:
        line = re.sub(key+r'= *\d*, .*',
                      key+'={date}0000,'.format(date=f"{int(conf[key]):02}"), line)

    for key in ['FDBFLAG']:
        line = re.sub(key+r'= *\d*, .*',
                      key+'={fdbflag},'.format(fdbflag=f"{conf[key]}"), line)

    outdata.append(line)

with open(conf['sandbox_dir']+'/input/COMMAND', 'w') as file:
    file.writelines(outdata)

# Generate AVAILABLE
if args.fdb is not True:
    lines = ["DATE     TIME        FILENAME\n", "YYYYMMDD HHMISS\n",
            "________ ______      __________________\n"]
    for adate in range(int(conf['IBDATE']), int(conf['IEDATE'])+1):
        for atime in range(int(conf['IBTIME']), int(conf['IETIME'])+1):
            filename = 'dispf'+str(adate)+f"{atime:02}"
            filepath = conf['sandbox_dir']+'/grib/'+filename
            if not os.path.exists(filepath) and args.s3 is True:
                download_file(filename, filepath)
            if not os.path.exists(filepath):
                raise RuntimeError("input grib file not found",
                                filepath)
            lines.append(str(adate)+' '+f"{atime:02}0000"+'      '+filename+'\n')
    with open(conf['sandbox_dir']+'/input/AVAILABLE', 'w') as file:
        file.writelines(lines)    

# Copy IGBP_int1.dat
shutil.copy(conf['landuse_data'], conf['sandbox_dir']+'/input/')
# Copy OUTGRID
shutil.copy(conf['flexpart_prefix']+'/share/options/OUTGRID.f',
            conf['sandbox_dir']+'/input/OUTGRID')

# Copy RECEPTORS
shutil.copy(conf['flexpart_prefix']+'/share/options/RECEPTORS',
            conf['sandbox_dir']+'/input/RECEPTORS')

# Generate RELEASES
releasefile = conf['flexpart_prefix']+'/share/options/RELEASES.'+conf['loc']
with open(releasefile, 'r') as file:
    filedata = file.readlines()

outdata = []
for line in filedata:
    # Replace the target string
    for key1, key2 in {'IDATE1': 'IBDATE',
                       'IDATE2': 'IEDATE'}.items():
        line = re.sub(key1+r' *= *\d*, .*',
                      key1+'={date},'.format(date=str(conf[key2])), line)

    for key1, key2 in {'ITIME1': 'IBTIME',
                       'ITIME2': 'IETIME'}.items():
        line = re.sub(key1+r' *= *\d*, .*',
                      key1+'={date}0000,'.format(date=f"{int(conf[key2]):02}"), line)

    outdata.append(line)

with open(conf['sandbox_dir']+'/input/RELEASES', 'w') as file:
    file.writelines(outdata)

# Copy SPECIES
shutil.copytree(conf['flexpart_prefix']+'/share/options/SPECIES',
                conf['sandbox_dir']+'/input/SPECIES')

# Copy surf data
for key in ['surfdata.t', 'surfdepo.t']:
    shutil.copy(conf['flexpart_prefix']+'/share/options/'+key,
                conf['sandbox_dir']+'/input/'+key)

# Generate pathnames
lines = [conf['sandbox_dir']+'/input/\n', conf['sandbox_dir']+'/output/\n',
         conf['sandbox_dir']+'/grib/\n', conf['sandbox_dir'] +
         '/input/AVAILABLE\n',
         '============================================\n']
with open(conf['sandbox_dir']+'/pathnames', 'w') as file:
    file.writelines(lines)

# Generate output
os.makedirs(conf['sandbox_dir']+'/output')

# Generate job
with open(conf['sandbox_dir']+'/job', 'w') as file:
    file.writelines(['ulimit -s unlimited\n', './FLEXPART\n'])
