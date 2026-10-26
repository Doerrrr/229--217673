import sys
from contract import cli
from validation import validate
from orbits import estimate
def main():return cli(validate,estimate)
if __name__=="__main__":sys.exit(main())
