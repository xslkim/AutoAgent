"""Prefer explicitly adopted source on ordinary launches; preview never changes adoption."""
import argparse
from compiler import DEFAULT_CACHE,read,read_package,compile_source,write_build
from versions import STORE,package_id,resolve

def selected_build(package,candidate=False,store=STORE,cache=DEFAULT_CACHE):
 package=package_id(package);pointer=store/'adopted'/(package+'.json')
 if candidate or not pointer.exists():return None
 adoption=read(pointer)
 if adoption.get('package')!=package:raise ValueError('Adopted pointer package mismatch')
 entry,source,manifest=resolve(package,adoption['source_revision'],store)
 return write_build(compile_source(source,source_manifest=manifest),cache)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('package');parser.add_argument('--candidate',action='store_true');args=parser.parse_args()
 path=selected_build(args.package,args.candidate)
 if path:print(path)
