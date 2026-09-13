"""Temporary compatibility alias for the renamed exam-prep entry point."""

from exam_prep import main


if __name__ == "__main__":
    raise SystemExit(main())
