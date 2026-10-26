import sys
from contract import cli
from algorithm import validate,solve
def main():return cli(validate,solve)
if __name__=="__main__":sys.exit(main())
