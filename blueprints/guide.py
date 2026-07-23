from flask import Blueprint, render_template
from services.data_service import DataService

guide_bp = Blueprint('guide', __name__, url_prefix='/guide')


@guide_bp.route("/")
def index():
    """攻略首页"""
    guides = DataService.get_guides()
    return render_template("guide_index.html", guides=guides)


@guide_bp.route("/<guide_id>")
def detail(guide_id):
    """攻略详情"""
    guide = DataService.get_guide(guide_id)
    if not guide:
        return "攻略不存在", 404
    return render_template("guide_detail.html", guide=guide, guide_id=guide_id)
