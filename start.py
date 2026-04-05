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
    analyzer = AuctionController()
    analyzer.fetch_commodities_data()
    analyzer.update_statics()
    analyzer.archive_old_files()
