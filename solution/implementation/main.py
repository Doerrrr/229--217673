import sys
from contract import cli
from algorithm import validate,solve,row_state
def main():return cli(validate,solve,row_state=row_state)
if __name__=="__main__":sys.exit(main())
