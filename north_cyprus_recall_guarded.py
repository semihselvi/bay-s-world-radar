import os

import main
import shard_runner
import north_cyprus_recall  # configures maximum-recall buyer rules
import north_cyprus_hunter_expansion  # verified public groups + free catalogs + wider single Exa query
import north_cyprus_spam_guard  # multilingual buyer patterns + service/recruitment rejection last


if __name__ == "__main__":
    os.environ["WORLD_RADAR_SHARD"] = "north_cyprus_hunter"
    shard_runner.SHARD = "north_cyprus_hunter"
    shard_runner.run()
