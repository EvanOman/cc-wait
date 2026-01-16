"""Entry point for running cc_wait as a module: python -m cc_wait"""

import sys

from cc_wait.hook import main

if __name__ == "__main__":
    sys.exit(main())
