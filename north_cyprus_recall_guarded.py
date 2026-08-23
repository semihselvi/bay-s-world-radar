import os

import main
import shard_runner
import north_cyprus_recall  # configures maximum-recall buyer rules
import north_cyprus_spam_guard  # layers recruitment/service-ad rejection last


if __name__ == "__main__":
    os.environ["WORLD_RADAR_SHARD"] = "north_cyprus_hunter"
    shard_runner.SHARD = "north_cyprus_hunter"
    shard_runner.run()
