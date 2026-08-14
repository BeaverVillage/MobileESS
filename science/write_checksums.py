#!/usr/bin/env python3
import hashlib,sys
from pathlib import Path
r=Path(sys.argv[1]);name=sys.argv[2] if len(sys.argv)>2 else "CHECKSUMS.sha256";rows=[]
for p in sorted(r.rglob("*")):
 if p.is_file() and not p.is_symlink() and p.name!=name and p.suffix!=".pyc" and "__pycache__" not in p.parts:
  h=hashlib.sha256()
  with p.open("rb") as f:
   for b in iter(lambda:f.read(8*1024*1024),b""):h.update(b)
  rows.append(f"{h.hexdigest()}  {p.relative_to(r).as_posix()}")
with (r/name).open("w",encoding="utf-8",newline="\n") as f:
 f.write("\n".join(rows)+"\n")
