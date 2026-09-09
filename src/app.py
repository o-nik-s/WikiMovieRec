"""WikiMovieRec API entry point — run with: python -m src.app  or  uvicorn src.app:app"""
import os
import uvicorn
from src.api import create_app

app = create_app()


def main():
    host = os.environ.get("WIKIMODREC_HOST", "0.0.0.0")
    port = int(os.environ.get("WIKIMODREC_PORT", "8000"))
    debug = os.environ.get("WIKIMODREC_DEBUG", "0") == "1"
    workers = int(os.environ.get("WIKIMODREC_WORKERS", "1"))
    uvicorn.run(
        "src.app:app",
        host=host,
        port=port,
        reload=debug,
        workers=1 if debug else workers,
    )


if __name__ == "__main__":
    main()