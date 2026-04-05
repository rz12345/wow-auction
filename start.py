from app.controllers.auction_controller import AuctionController

if __name__ == '__main__':
    analyzer = AuctionController()
    analyzer.fetch_commodities_data()
    analyzer.update_statics()
    analyzer.archive_old_files()