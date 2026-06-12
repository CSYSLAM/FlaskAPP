from services.data_service import DataService


class Location:
    _locations = None

    @classmethod
    def get_location(cls, location_id):
        locations = DataService.get_locations()
        return locations.get(location_id)

    @classmethod
    def get_locations(cls):
        return DataService.get_locations()

    @classmethod
    def get_all_location_ids(cls):
        return list(DataService.get_locations().keys())
