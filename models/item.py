from services.data_service import DataService


class Item:
    @classmethod
    def get_item(cls, item_id):
        items = DataService.get_items()
        return items.get(item_id)

    @classmethod
    def get_all_items(cls):
        return DataService.get_items()
