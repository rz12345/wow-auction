import logging
import os
from app.controllers.auction_controller import AuctionController

def setup_logging():
    os.makedirs('logs', exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/app.log', encoding='utf-8'),
            logging.StreamHandler(),
        ]
    )

if __name__ == '__main__':
    setup_logging()
    logger = logging.getLogger(__name__)
    try:
        analyzer = AuctionController()
    except RuntimeError as e:
        logger.critical("初始化失敗，程式終止：%s", e)
        raise SystemExit(1)
    analyzer.fetch_commodities_data()
    analyzer.update_statics()
    analyzer.archive_old_files()
