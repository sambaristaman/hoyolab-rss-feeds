import argparse
import asyncio
import logging
from pathlib import Path
from platform import system
from typing import Optional

from .configs import FeedConfigLoader
from .feeds import GameFeedCollection

logger = logging.getLogger(__package__)


async def create_feeds(args) -> None:
    # fallback path defined in config loader if no path given
    config_loader = FeedConfigLoader(args.config_path)

    if not config_loader.path.exists():
        await config_loader.create_default_config_file()
        logger.info("Default config file created at %s.", config_loader.path.resolve())
        return

    feed_configs = await config_loader.get_all_feed_configs()

    # If no aggregate requested, keep the original behavior (one feed per game).
    if not args.single_feed_path:
        game_feed = GameFeedCollection.from_configs(feed_configs)
        await game_feed.create_feeds()
        return

   # Aggregate mode: fetch items for all games, merge, then write once.
    collection = GameFeedCollection.from_configs(feed_configs)

    import aiohttp
    from .models import FeedFileWriterConfig, FeedType, FeedMeta
    from .writers import JSONFeedFileWriter, AtomFeedFileWriter
    from pydantic import parse_obj_as, HttpUrl

    async with aiohttp.ClientSession() as session:
        all_items = []
        for gf in collection._game_feeds:  # reuse internal list
            items = await gf.fetch_items(session)
            all_items.extend(items)
        # sort newest first by id (matches existing behavior)
        all_items.sort(key=lambda item: item.id, reverse=True)

    # Build aggregate meta (pick language from the first feed; override title/home/icon).
    first_meta = feed_configs[0].feed_meta
    agg_meta = FeedMeta(
        game=first_meta.game,  # still required; harmless placeholder
        language=first_meta.language,
        title=args.single_feed_title,
        icon=(parse_obj_as(HttpUrl, args.single_icon) if args.single_icon else None),
        home_page_url=parse_obj_as(HttpUrl, args.single_home_url),
        category_size=first_meta.category_size,
        categories=first_meta.categories,
    )

    feed_type = FeedType.JSON if args.single_feed_format == "json" else FeedType.ATOM
    writer_conf = FeedFileWriterConfig(feed_type=feed_type, path=args.single_feed_path)
    writer = JSONFeedFileWriter(writer_conf) if feed_type == FeedType.JSON else AtomFeedFileWriter(writer_conf)
    await writer.write_feed(agg_meta, all_items)


def cli() -> None:
    if system() == "Windows":
        # default policy not working on windows
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore

    arg_parser = argparse.ArgumentParser(
        prog="hoyolab-rss-feeds", description="Generate Hoyolab RSS feeds."
    )

    arg_parser.add_argument(
        "-c", "--config-path", help="Path to the TOML config file", type=Path
    )

    # Aggregate (single feed) options
    arg_parser.add_argument(
        "--single-feed-path",
        type=Path,
        help="Write ONE aggregated feed (instead of one per game) to this path.",
    )
    arg_parser.add_argument(
        "--single-feed-format",
        choices=("json", "atom"),
        default="json",
        help="Format for the aggregated feed (default: json).",
    )
    arg_parser.add_argument(
        "--single-feed-title",
        type=str,
        default="Hoyolab — All Games",
        help="Title for the aggregated feed.",
    )
    arg_parser.add_argument(
        "--single-home-url",
        type=str,
        default="https://www.hoyolab.com/",
        help="Home page URL used in the aggregated feed metadata.",
   )
    arg_parser.add_argument(
        "--single-icon",
        type=str,
        help="Optional icon URL for the aggregated feed.",
    )

    arg_parser.add_argument(
        "-l",
        "--log-path",
        required=False,
        default=None,
        help="Path to the written log file",
        type=Path,
    )

    args = arg_parser.parse_args()

    logging.basicConfig(
        filename=args.log_path,
        filemode="a",
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        level=logging.INFO,
    )

    asyncio.run(create_feeds(args))


if __name__ == "__main__":
    cli()
