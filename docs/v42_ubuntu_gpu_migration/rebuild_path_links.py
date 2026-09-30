"""Read-only complete alias/reparse inventory; never follows reparse directories."""
import os,stat,json
from pathlib import Path
O=Path(__file__).absolute().parent
roots=['C:/codex_mobileess_workspace','C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS','C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2','D:/ChatGPT/Mobile ESS','D:/ChatGPT/Mobile ESS 2','D:/codex_mobileess_workspace']
links=[];errors=[]
def link(p):
    try:
        if os.lstat(p).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            try:target=os.readlink(p)
            except ValueError:target='NON_LINK_REPARSE_METADATA_DO_NOT_DELETE'
            links.append(dict(path=str(Path(p).absolute()),target=target));return True
    except OSError as e:errors.append(dict(path=str(p),error=str(e)));return True
    return False
for root in roots:
    if not os.path.exists(root) or link(root):continue
    for folder,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=[d for d in dirs if not link(os.path.join(folder,d))]
(O/'WINDOWS_PATH_LINKS.json').write_text(json.dumps(dict(roots=roots,links=links,errors=errors,WSL_storage_excluded='D:/WSL',follow_reparse=False),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('PATH_LINKS',len(links),'ERRORS',len(errors),flush=True)
