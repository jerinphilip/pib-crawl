from . import db
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy import func, select
import datetime

class Entry(db.Model):
    __tablename__ = 'entry'
    __searchable__ = ['content']
    id = db.Column('id', db.Integer, primary_key = True)
    lang = db.Column(db.String(100))
    date = db.Column(db.DateTime, default=datetime.datetime.utcnow, index=True)
    content = db.Column(db.Text)
    place = db.Column(db.String(100))
    neighbors = db.relationship("Link", primaryjoin="Link.first_id==Entry.id")
    translations = db.relationship("Translation", backref="entry")

    @hybrid_property
    def link_count(self):
        return self.finalized.count()
    
    @link_count.expression
    def link_count(cls):
        return (
            select([func.count(Link.other_id)]).
                where(Link.anchor_id == cls.id).
                label("link_count")
        )


class Link(db.Model):
    __tablename__ = 'link'
    __table_args__ = (
        db.UniqueConstraint('first_id', 'second_id', name='unique_first_second'),
    )
    id = db.Column('id', db.Integer, primary_key = True)
    first_id = db.Column(db.Integer, db.ForeignKey('entry.id'))
    second_id = db.Column(db.Integer, db.ForeignKey('entry.id'))
    first = db.relationship('Entry',foreign_keys=[first_id])
    second = db.relationship('Entry',foreign_keys=[second_id])

class Translation(db.Model):
    __tablename__ = 'translation'
    __table_args__ = (
        db.UniqueConstraint('parent_id', 'model', name='unique_parent_model'),
    )

    __searchable__ = ['translated']
    id = db.Column('id', db.Integer, primary_key = True)
    parent_id = db.Column(db.Integer, db.ForeignKey('entry.id'), nullable=False)
    model = db.Column(db.String(100))
    lang = db.Column(db.String(100))
    translated = db.Column(db.Text)

db.create_all()


