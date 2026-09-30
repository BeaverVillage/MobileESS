"""Complete native physical domains with all 96 electrical slots."""
from .config import PRIMARY
from v42_root.real import main
if __name__=='__main__':main(kinds=['F2']+PRIMARY[1:])
