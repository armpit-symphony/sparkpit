import sys
from pathlib import Path

# Add parent directory to path to import sparkpit module
sys.path.insert(0, str(Path(__file__).parent.parent))

from sparkpit.seed_demo import main


if __name__ == "__main__":
    main()
