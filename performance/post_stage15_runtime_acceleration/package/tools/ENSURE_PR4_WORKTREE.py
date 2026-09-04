#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,subprocess
from pathlib import Path

PR4="06a94bccc0a232ae7ea09cbc7b00962162c10f4d"
SCIENCE_SHA="1177ac8814f1008907f89ebf513bf9fe3e469d2c09a51ba85303c46c428f76b9"
TARGET=Path("/home/jaewon/mobile_ess_work/source_worktrees")/f"pr4_{PR4[:12]}"

def sha(p:Path)->str:
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()

def git(repo:Path,*args:str,check=True)->str:
 cp=subprocess.run(["git","-C",str(repo),*args],text=True,capture_output=True)
 if check and cp.returncode:
  raise RuntimeError(f"git {' '.join(args)} failed: {cp.stderr.strip()}")
 return cp.stdout.strip()

def find_repo(explicit:str|None)->Path:
 c=[]
 if explicit:c.append(Path(explicit))
 if os.getenv("MOBILEESS_REPO"):c.append(Path(os.environ["MOBILEESS_REPO"]))
 c += [
  Path("/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS/github_MobileESS"),
  Path("/mnt/c/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/github_MobileESS"),
  Path("/mnt/c/Users/kjw39/OneDrive/Documents/ChatGPT/Mobile ESS/github_MobileESS"),
  Path.home()/"MobileESS",
 ]
 for p in c:
  if (p/".git").exists():return p.resolve()
 raise RuntimeError("MobileESS git repository not found; pass --repo")

def main():
 ap=argparse.ArgumentParser();ap.add_argument("--repo");ap.add_argument("--print-only",action="store_true");a=ap.parse_args()
 repo=find_repo(a.repo)
 if subprocess.run(["git","-C",str(repo),"cat-file","-e",f"{PR4}^{{commit}}"],capture_output=True).returncode:
  raise RuntimeError(f"required PR4 commit {PR4} is not present in local git object database; fetch PR4 first")
 if TARGET.exists():
  if not (TARGET/".git").exists():raise RuntimeError(f"existing worktree target is not a git worktree: {TARGET}")
  head=git(TARGET,"rev-parse","HEAD")
  if head!=PR4:raise RuntimeError(f"PR4 worktree HEAD drift: {head}")
 else:
  TARGET.parent.mkdir(parents=True,exist_ok=True)
  cp=subprocess.run(["git","-C",str(repo),"worktree","add","--detach",str(TARGET),PR4],text=True,capture_output=True)
  if cp.returncode:raise RuntimeError("git worktree add failed: "+cp.stderr.strip())
 if sha(TARGET/"science/main.py")!=SCIENCE_SHA:raise RuntimeError("PR4 worktree science/main.py SHA drift")
 rec={"status":"PASS","repository":str(repo),"worktree":str(TARGET),"head":PR4,"science_main_sha256":SCIENCE_SHA}
 print(json.dumps(rec,indent=2))
 return 0
if __name__=="__main__":raise SystemExit(main())
