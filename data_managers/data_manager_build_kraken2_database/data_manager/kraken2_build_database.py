#!/usr/bin/env python

import argparse
import datetime
import errno
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from enum import Enum

try:
    # Python3
    from urllib.request import urlopen
    from urllib.error import URLError
except ImportError:
    from urllib2 import urlopen
    from urllib2 import URLError


DATA_TABLE_NAME = "kraken2_databases"


class KrakenDatabaseTypes(Enum):
    standard_local_build = 'standard_local_build'
    standard_prebuilt = 'standard_prebuilt'
    minikraken = 'minikraken'
    special_prebuilt = 'special_prebuilt'
    special = 'special'
    custom = 'custom'

    def __str__(self):
        return self.value


class SpecialDatabaseTypes(Enum):
    rdp = 'rdp'
    greengenes = 'greengenes'
    silva = 'silva'

    def __str__(self):
        return self.value


class Minikraken2Versions(Enum):
    v1 = 'v1'
    v2 = 'v2'

    def __str__(self):
        return self.value


class StandardPrebuiltSizes(Enum):
    viral = "viral"
    minusb = "minusb"
    standard = "standard"
    standard_08gb = "standard_08gb"
    standard_16gb = "standard_16gb"
    pluspf = "pluspf"
    pluspf_08gb = "pluspf_08gb"
    pluspf_16gb = "pluspf_16gb"
    pluspfp = "pluspfp"
    pluspfp_08gb = "pluspfp_08gb"
    pluspfp_16gb = "pluspfp_16gb"
    eupathdb48 = "eupathdb48"

    def __str__(self):
        return self.value


def kraken2_build_standard(kraken2_args, target_directory, data_table_name=DATA_TABLE_NAME):
    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H%M%SZ")

    database_value = "_".join([
        now,
        "standard",
        "kmer-len", str(kraken2_args["kmer_len"]),
        "minimizer-len", str(kraken2_args["minimizer_len"]),
        "minimizer-spaces", str(kraken2_args["minimizer_spaces"]),
        "load-factor", str(kraken2_args["load_factor"]),
    ])

    database_name = " ".join([
        "Standard (Local Build)",
        "(Created:",
        now + ",",
        "kmer-len=" + str(kraken2_args["kmer_len"]) + ",",
        "minimizer-len=" + str(kraken2_args["minimizer_len"]) + ",",
        "minimizer-spaces=" + str(kraken2_args["minimizer_spaces"]) + ")",
        "load-factor", str(kraken2_args["load_factor"]),
    ])

    database_path = database_value

    args = [
        '--threads', str(kraken2_args["threads"]),
        '--standard',
        '--kmer-len', str(kraken2_args["kmer_len"]),
        '--minimizer-len', str(kraken2_args["minimizer_len"]),
        '--minimizer-spaces', str(kraken2_args["minimizer_spaces"]),
        '--load-factor', str(kraken2_args["load_factor"]),
        '--db', database_path
    ]

    subprocess.check_call(['kraken2-build'] + args, cwd=target_directory)

    if kraken2_args["clean"]:
        args = [
            '--threads', str(kraken2_args["threads"]),
            '--clean',
            '--db', database_path
        ]

        subprocess.check_call(['kraken2-build'] + args, cwd=target_directory)

    data_table_entry = {
        'data_tables': {
            data_table_name: [
                {
                    "value": database_value,
                    "name": database_name,
                    "path": database_path,
                }
            ]
        }
    }

    return data_table_entry


def kraken2_build_standard_prebuilt(prebuilt_db, prebuilt_date, target_directory, data_table_name=DATA_TABLE_NAME):

    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H%M%SZ")

    prebuild_name = {
        'viral': "Viral",
        'minusb': "MinusB (archaea, viral, plasmid, human, UniVec_Core)",
        'standard': "Standard-Full (archaea, bacteria, viral, plasmid, human,UniVec_Core)",
        'standard_08gb': "Standard-8 (Standard with DB capped at 8 GB)",
        'standard_16gb': "Standard-16 (Standard with DB capped at 16 GB)",
        'pluspf': "PlusPF (Standard plus protozoa and fungi)",
        'pluspf_08gb': "PlusPF-8 (PlusPF with DB capped at 8 GB)",
        'pluspf_16gb': "PlusPF-16 (PlusPF with DB capped at 16 GB)",
        'pluspfp': "PlusPFP (Standard plus protozoa, fungi and plant)",
        'pluspfp_08gb': "PlusPFP-8 (PlusPFP with DB capped at 8 GB)",
        'pluspfp_16gb': "PlusPFP-16 (PlusPFP with DB capped at 16 GB)",
        'eupathdb48': "EuPathDB-46",
    }

    database_value = "_".join([
        now,
        "standard_prebuilt",
        prebuilt_db,
        prebuilt_date
    ])

    database_name = " ".join([
        "Prebuilt Refseq indexes: ",
        prebuild_name[prebuilt_db],
        "(Version: ",
        prebuilt_date,
        "- Downloaded:",
        now + ")"
    ])

    database_path = database_value

    # we may need to let the user choose the date when new DBs are posted.
    date_url_str = prebuilt_date.replace('-', '')
    # download the pre-built database
    try:
        download_url = 'https://genome-idx.s3.amazonaws.com/kraken/k2_%s_%s.tar.gz' % (prebuilt_db, date_url_str)
        src = urlopen(download_url)
    except URLError as e:
        print('url: ' + download_url, file=sys.stderr)
        print(e, file=sys.stderr)
        exit(1)

    with open('tmp_data.tar.gz', 'wb') as dst:
        shutil.copyfileobj(src, dst)
    # unpack the downloaded archive to the target directory
    with tarfile.open('tmp_data.tar.gz', 'r:gz') as fh:
        for member in fh.getmembers():
            if member.isreg():
                member.name = os.path.basename(member.name)
                fh.extract(member, os.path.join(target_directory, database_path))

    data_table_entry = {
        'data_tables': {
            data_table_name: [
                {
                    "value": database_value,
                    "name": database_name,
                    "path": database_path,
                }
            ]
        }
    }

    return data_table_entry


def kraken2_build_minikraken(minikraken2_version, target_directory, data_table_name=DATA_TABLE_NAME):

    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H%M%SZ")

    database_value = "_".join([
        now,
        "minikraken2",
        minikraken2_version,
        "8GB",
    ])

    database_name = " ".join([
        "Minikraken2",
        minikraken2_version,
        "(Created:",
        now + ")"
    ])

    database_path = database_value

    # download the minikraken2 data
    try:
        download_url = 'https://genome-idx.s3.amazonaws.com/kraken/minikraken2_%s_8GB_201904.tgz' % minikraken2_version
        src = urlopen(download_url)
    except URLError as e:
        print('url: ' + download_url, file=sys.stderr)
        print(e, file=sys.stderr)
        exit(1)

    with open('tmp_data.tar.gz', 'wb') as dst:
        shutil.copyfileobj(src, dst)
    # unpack the downloaded archive to the target directory
    with tarfile.open('tmp_data.tar.gz', 'r:gz') as fh:
        for member in fh.getmembers():
            if member.isreg():
                member.name = os.path.basename(member.name)
                fh.extract(member, os.path.join(target_directory, database_path))

    data_table_entry = {
        'data_tables': {
            data_table_name: [
                {
                    "value": database_value,
                    "name": database_name,
                    "path": database_path,
                }
            ]
        }
    }

    return data_table_entry


def kraken2_build_special(kraken2_args, target_directory, data_table_name=DATA_TABLE_NAME):

    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H%M%SZ")

    special_database_names = {
        "rdp": "RDP",
        "greengenes": "Greengenes",
        "silva": "Silva",
    }

    database_value = "_".join([
        now,
        kraken2_args["special_database_type"],
        "kmer-len", str(kraken2_args["kmer_len"]),
        "minimizer-len", str(kraken2_args["minimizer_len"]),
        "minimizer-spaces", str(kraken2_args["minimizer_spaces"]),
        "load-factor", str(kraken2_args["load_factor"]),
    ])

    database_name = " ".join([
        special_database_names[kraken2_args["special_database_type"]],
        "(Created:",
        now + ",",
        "kmer-len=" + str(kraken2_args["kmer_len"]) + ",",
        "minimizer-len=" + str(kraken2_args["minimizer_len"]) + ",",
        "minimizer-spaces=" + str(kraken2_args["minimizer_spaces"]) + ")",
        "load-factor=" + str(kraken2_args["load_factor"]) + ")",
    ])

    database_path = database_value

    args = [
        '--threads', str(kraken2_args["threads"]),
        '--special', kraken2_args["special_database_type"],
        '--kmer-len', str(kraken2_args["kmer_len"]),
        '--minimizer-len', str(kraken2_args["minimizer_len"]),
        '--minimizer-spaces', str(kraken2_args["minimizer_spaces"]),
        '--load-factor', str(kraken2_args["load_factor"]),
        '--db', database_path
    ]

    subprocess.check_call(['kraken2-build'] + args, cwd=target_directory)

    if kraken2_args["clean"]:
        args = [
            '--threads', str(kraken2_args["threads"]),
            '--clean',
            '--db', database_path
        ]

        subprocess.check_call(['kraken2-build'] + args, cwd=target_directory)

    data_table_entry = {
        'data_tables': {
            data_table_name: [
                {
                    "value": database_value,
                    "name": database_name,
                    "path": database_path,
                }
            ]
        }
    }

    return data_table_entry


def kraken2_build_custom(kraken2_args, custom_database_name, custom_source_info, target_directory, data_table_name=DATA_TABLE_NAME):
    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H%M%SZ")

    database_value = "_".join([
        now,
        re.sub(r'[^\w_.-]+', '_', custom_database_name).strip('_'),
        "kmer-len", str(kraken2_args["kmer_len"]),
        "minimizer-len", str(kraken2_args["minimizer_len"]),
        "minimizer-spaces", str(kraken2_args["minimizer_spaces"]),
        "load-factor", str(kraken2_args["load_factor"]),
    ])

    database_name = " ".join([
        custom_database_name,
        "(" + custom_source_info + ",",
        "kmer-len=" + str(kraken2_args["kmer_len"]) + ",",
        "minimizer-len=" + str(kraken2_args["minimizer_len"]) + ",",
        "minimizer-spaces=" + str(kraken2_args["minimizer_spaces"]) + ",",
        "load-factor=" + str(kraken2_args["load_factor"]) + ")",
    ])

    database_path = database_value

    args = [
        '--threads', str(kraken2_args["threads"]),
        '--download-taxonomy',
        '--db', database_path,
    ]

    if kraken2_args['skip_maps']:
        args.append('--skip-maps')

    subprocess.check_call(['kraken2-build'] + args, cwd=target_directory)

    args = [
        '--threads', str(kraken2_args["threads"]),
        '--add-to-library', kraken2_args["custom_fasta"],
        '--db', database_path,
    ]

    subprocess.check_call(['kraken2-build'] + args, cwd=target_directory)

    args = [
        '--threads', str(kraken2_args["threads"]),
        '--build',
        '--kmer-len', str(kraken2_args["kmer_len"]),
        '--minimizer-len', str(kraken2_args["minimizer_len"]),
        '--minimizer-spaces', str(kraken2_args["minimizer_spaces"]),
        '--load-factor', str(kraken2_args["load_factor"]),
        '--db', database_path,
    ]

    subprocess.check_call(['kraken2-build'] + args, cwd=target_directory)

    if kraken2_args["clean"]:
        args = [
            '--threads', str(kraken2_args["threads"]),
            '--clean',
            '--db', database_path,
        ]

        subprocess.check_call(['kraken2-build'] + args, cwd=target_directory)

    data_table_entry = {
        'data_tables': {
            data_table_name: [
                {
                    "value": database_value,
                    "name": database_name,
                    "path": database_path,
                }
            ]
        }
    }

    return data_table_entry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('data_manager_json')
    parser.add_argument('--kmer-len', dest='kmer_len', type=int, default=35, help='kmer length')
    parser.add_argument('--minimizer-len', dest='minimizer_len', type=int, default=31, help='minimizer length')
    parser.add_argument('--minimizer-spaces', dest='minimizer_spaces', default=6, help='minimizer spaces')
    parser.add_argument('--load-factor', dest='load_factor', type=float, default=0.7, help='load factor')
    parser.add_argument('--threads', dest='threads', default=1, help='threads')
    parser.add_argument('--database-type', dest='database_type', type=KrakenDatabaseTypes, choices=list(KrakenDatabaseTypes), required=True, help='type of kraken database to build')
    parser.add_argument('--minikraken2-version', dest='minikraken2_version', type=Minikraken2Versions, choices=list(Minikraken2Versions), help='MiniKraken2 version (only applies to --database-type minikraken)')
    parser.add_argument('--prebuilt-db', dest='prebuilt_db', type=StandardPrebuiltSizes, choices=list(StandardPrebuiltSizes), help='Prebuilt database to download. Only applies to --database-type standard_prebuilt or special_prebuilt.')
    parser.add_argument('--prebuilt-date', dest='prebuilt_date', help='Database build date (YYYY-MM-DD). Only applies to --database-type standard_prebuilt.')
    parser.add_argument('--special-database-type', dest='special_database_type', type=SpecialDatabaseTypes, choices=list(SpecialDatabaseTypes), help='type of special database to build (only applies to --database-type special)')
    parser.add_argument('--custom-fasta', dest='custom_fasta', help='fasta file for custom database (only applies to --database-type custom)')
    parser.add_argument('--custom-database-name', dest='custom_database_name', help='Name for custom database (only applies to --database-type custom)')
    parser.add_argument('--custom-source-info', dest='custom_source_info', help='Description of how this build has been sourced (only applies to --database-type custom)')
    parser.add_argument('--skip-maps', dest='skip_maps', action='store_true', help='')
    parser.add_argument('--clean', dest='clean', action='store_true', help='Clean up extra files')
    args = parser.parse_args()

    with open(args.data_manager_json) as fh:
        data_manager_input = json.load(fh)

    target_directory = data_manager_input['output_data'][0]['extra_files_path']

    try:
        os.mkdir(target_directory)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(target_directory):
            pass
        else:
            raise

    data_manager_output = {}

    if str(args.database_type) == 'standard_local_build':
        kraken2_args = {
            "kmer_len": args.kmer_len,
            "minimizer_len": args.minimizer_len,
            "minimizer_spaces": args.minimizer_spaces,
            "load_factor": args.load_factor,
            "threads": args.threads,
            "clean": args.clean,
        }
        data_manager_output = kraken2_build_standard(
            kraken2_args,
            target_directory,
        )
    elif str(args.database_type) in ('standard_prebuilt', 'special_prebuilt'):
        data_manager_output = kraken2_build_standard_prebuilt(
            str(args.prebuilt_db),
            str(args.prebuilt_date),
            target_directory
        )
    elif str(args.database_type) == 'minikraken':
        data_manager_output = kraken2_build_minikraken(
            str(args.minikraken2_version),
            target_directory
        )
    elif str(args.database_type) == 'special':
        kraken2_args = {
            "special_database_type": str(args.special_database_type),
            "kmer_len": args.kmer_len,
            "minimizer_len": args.minimizer_len,
            "minimizer_spaces": args.minimizer_spaces,
            "load_factor": args.load_factor,
            "threads": args.threads,
            "clean": args.clean,
        }
        data_manager_output = kraken2_build_special(
            kraken2_args,
            target_directory,
        )
    elif str(args.database_type) == 'custom':
        kraken2_args = {
            "custom_fasta": args.custom_fasta,
            "skip_maps": args.skip_maps,
            "kmer_len": args.kmer_len,
            "minimizer_len": args.minimizer_len,
            "minimizer_spaces": args.minimizer_spaces,
            "load_factor": args.load_factor,
            "threads": args.threads,
            "clean": args.clean,
        }
        data_manager_output = kraken2_build_custom(
            kraken2_args,
            args.custom_database_name,
            args.custom_source_info,
            target_directory,
        )
    else:
        sys.exit("Invalid database type")

    with open(args.data_manager_json, 'w') as fh:
        json.dump(data_manager_output, fh, sort_keys=True)


if __name__ == "__main__":
    main()
