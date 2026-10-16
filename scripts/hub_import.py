#!/usr/bin/env python3
"""Offline opaque payload uploader; Core owns verification/staging, never execution."""
import argparse,json,os,socket,stat,uuid
from pathlib import Path

def upload(root,plugin_id,source):
    counter=0;active=None
    def call(op,**fields):
        nonlocal counter
        counter+=1
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(5);connection.connect(str(Path(root)/'core.sock'))
            connection.sendall((json.dumps({'version':1,'request_id':f'import_{token}_{counter}','op':op,**fields})+'\n').encode())
            data=b''
            while not data.endswith(b'\n'):
                chunk=connection.recv(65536)
                if not chunk:raise RuntimeError('Core disconnected')
                data+=chunk
                if len(data)>65536:raise RuntimeError('oversized response')
            result=json.loads(data)
            if result['code']!='ok':raise RuntimeError(result['code'])
            return result
    token=uuid.uuid4().hex[:16]
    fd=os.open(source,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        with os.fdopen(fd,'rb') as file:
            metadata=os.fstat(file.fileno())
            if not stat.S_ISREG(metadata.st_mode):raise ValueError('source must be a regular file')
            snap=call('snapshot');hub=snap.get('hub') or {};entry=next((e for e in hub.get('entries',[]) if e['plugin_id']==plugin_id),None)
            if entry is None:raise ValueError('unknown_plugin')
            if metadata.st_size!=entry['download_size']:raise ValueError('payload_size_mismatch')
            begin=call('hub_begin',revision=hub['approval_revision'],plugin_id=plugin_id,manifest_sha256=entry['manifest_sha256']);active=begin['hub']['import']['import_id'];offset=0
            while True:
                chunk=file.read(1024)
                if not chunk:break
                call('hub_chunk',import_id=active,offset=offset,hex=chunk.hex());offset+=len(chunk)
            final=call('hub_finish',import_id=active);active=None
            return final
    finally:
        if active is not None:
            try:call('hub_abort',import_id=active)
            except (OSError,ValueError,RuntimeError):pass

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--plugin',required=True);parser.add_argument('--source',required=True);args=parser.parse_args()
    print(json.dumps(upload(args.root,args.plugin,args.source)))
