"""One bounded subprocess per PDF. Never opens a network connection or runs OCR."""

import argparse
import resource
from pathlib import Path

from app.parsing.contracts import ParseOptions
from app.parsing.engine import parse_pdf


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("options")
    args = parser.parse_args()
    # Bound generated diagnostics/JSON on POSIX. This is crash/timeout isolation,
    # not a hostile-document OS sandbox or a promise of constant memory usage.
    resource.setrlimit(resource.RLIMIT_FSIZE, (256 * 1024 * 1024, 256 * 1024 * 1024))
    result = parse_pdf(args.input, ParseOptions.model_validate_json(args.options))
    with args.output.open("x", encoding="utf-8") as output:
        output.write(result.model_dump_json())


if __name__ == "__main__":
    main()
