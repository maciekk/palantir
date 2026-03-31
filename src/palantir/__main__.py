import argparse

from palantir.app import PalantirApp


def main() -> None:
    parser = argparse.ArgumentParser(prog="palantir", description="CLI news reader")
    parser.add_argument(
        "--width",
        type=int,
        default=120,
        metavar="N",
        help="Max line width for article body (0 = no limit, default: 120)",
    )
    parser.add_argument(
        "--llm-model",
        default="llama3.2",
        metavar="MODEL",
        help="Ollama model for AI summaries (default: llama3.2)",
    )
    args = parser.parse_args()
    PalantirApp(max_width=args.width, llm_model=args.llm_model).run()


if __name__ == "__main__":
    main()
