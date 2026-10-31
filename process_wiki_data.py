"""Process the wiki_data after it is loaded by load_wiki_data.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import create_point_accumulations, init_db


def main():
    init_db()
    create_point_accumulations()
    


if __name__ == "__main__":
    main()