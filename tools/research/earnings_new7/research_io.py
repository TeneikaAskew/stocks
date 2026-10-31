"""Explicit owner-supplied private inputs. No acquisition or network client.

Run entrypoints with --input-root DIR and optional --path-map JSON. The mapping
rebinds captured absolute input prefixes to owner's local copies. Results stay
in that private root; the renderer exposes only derived outputs in its public
subdirectory. Never point this at a public checkout with licensed raw payloads.
"""
import argparse
import json
from pathlib import Path

_root = None
_prefixes = []


def selected_root():
    global _root, _prefixes
    if _root is None:
        parser=argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--input-root',required=True,type=Path)
        parser.add_argument('--path-map',type=Path)
        args=parser.parse_args()
        _root=args.input_root.resolve(strict=True)
        if args.path_map:
            mapping=json.loads(args.path_map.read_text())
            if not isinstance(mapping,dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in mapping.items()):
                raise ValueError('path map must map captured input prefixes to local directories')
            _prefixes=sorted(((Path(k),Path(v).resolve(strict=True)) for k,v in mapping.items()),key=lambda pair:len(str(pair[0])),reverse=True)
    return _root


def mapped_path(value):
    path=Path(value)
    for old,new in _prefixes:
        try:return new/path.relative_to(old)
        except ValueError:continue
    return path


NEW7=('FDX','LLY','STX','INTC','AMD','TWLO','VLO')


def check_new7_protocol(protocol):
    """Reject unrelated ten-row runners before opening any response/outcome."""
    if tuple(protocol.get('order',())) != NEW7 or tuple(e.get('ticker') for e in protocol.get('events',())) != NEW7:
        raise ValueError('only the preserved seven-ticker cohort is admitted')
    return protocol
