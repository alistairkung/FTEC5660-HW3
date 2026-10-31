"""Optional CLI lifecycle wrapper; leaves the lecturer's runner untouched."""

import hw3
from observability import Tracing


def main() -> int:
    hw3.load_env_file()
    with Tracing() as tracing:
        with tracing.observation("hw3-run") as observation:
            status = hw3.main()
            observation.update(output={"exit_code": status})
            return status


if __name__ == "__main__":
    raise SystemExit(main())
