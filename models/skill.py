from services.data_service import DataService


class Skill:
    @classmethod
    def get_skill(cls, skill_id):
        skills = DataService.get_skills()
        return skills.get(skill_id)

    @classmethod
    def get_all_skills(cls):
        return DataService.get_skills()
