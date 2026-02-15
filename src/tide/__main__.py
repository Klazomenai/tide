"""Allow running as python -m tide."""

import asyncio

from tide.main import main

if __name__ == "__main__":
    asyncio.run(main())
