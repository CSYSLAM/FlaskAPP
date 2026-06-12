from services.data_service import DataService


class EquipmentTemplate:
    @classmethod
    def get_template(cls, template_id):
        return DataService.get_equipment_template(template_id)

    @classmethod
    def get_all_templates(cls):
        return DataService.get_equipment_templates()
