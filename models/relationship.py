"""Relationship model for social connections (红颜/知己)."""
from services import db


class Relationship(db.Model):
    __tablename__ = 'relationship'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    player1_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    player2_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)

    # Type: 'hongyan' (红颜) or 'zhiji' (知己)
    rel_type = db.Column(db.String(20), nullable=False)

    # Fate value (缘分值)
    fate_value = db.Column(db.Integer, default=0)

    # Who initiated the relationship
    initiator_id = db.Column(db.Integer, nullable=False)

    @property
    def type_name(self):
        names = {'hongyan': '红颜', 'zhiji': '知己', 'spouse': '夫妻', 'pending': '待定'}
        return names.get(self.rel_type, self.rel_type)

    @classmethod
    def get_relationship(cls, player1_id, player2_id):
        """Get relationship between two players."""
        rel = cls.query.filter(
            ((cls.player1_id == player1_id) & (cls.player2_id == player2_id)) |
            ((cls.player1_id == player2_id) & (cls.player2_id == player1_id))
        ).first()
        return rel

    @classmethod
    def get_relationships(cls, player_id, rel_type=None):
        """Get all relationships for a player."""
        query = cls.query.filter(
            (cls.player1_id == player_id) | (cls.player2_id == player_id)
        )
        if rel_type:
            query = query.filter_by(rel_type=rel_type)
        return query.all()

    @classmethod
    def count_relationships(cls, player_id, rel_type=None):
        """Count relationships for a player."""
        query = cls.query.filter(
            (cls.player1_id == player_id) | (cls.player2_id == player_id)
        )
        if rel_type:
            query = query.filter_by(rel_type=rel_type)
        return query.count()

    def get_other_player_id(self, player_id):
        """Get the other player's ID in this relationship."""
        return self.player2_id if self.player1_id == player_id else self.player1_id
