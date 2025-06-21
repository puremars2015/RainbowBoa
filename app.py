import os
from datetime import datetime
from flask import Flask, request, jsonify, render_template, session
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///blog.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev')

db = SQLAlchemy(app)
CORS(app)

post_tags = db.Table(
    "post_tags",
    db.Column("post_id", db.Integer, db.ForeignKey("post.id"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tag.id"), primary_key=True),
)


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    def to_dict(self):
        return {"id": self.id, "name": self.name}


class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    def to_dict(self):
        return {"id": self.id, "name": self.name}


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"))
    likes = db.Column(db.Integer, default=0)

    category = db.relationship("Category", backref=db.backref("posts", lazy=True))
    tags = db.relationship("Tag", secondary=post_tags, backref=db.backref("posts", lazy="dynamic"))

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "category": self.category.name if self.category else None,
            "tags": [t.name for t in self.tags],
            "likes": self.likes,
        }


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    post = db.relationship("Post", backref=db.backref("comments", lazy=True))

    def to_dict(self):
        return {
            "id": self.id,
            "author": self.author,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
        }

with app.app_context():
    db.create_all()

@app.route('/api/posts', methods=['GET'])
def get_posts():
    query = Post.query
    category = request.args.get('category')
    tag = request.args.get('tag')
    search = request.args.get('search')
    if category:
        query = query.join(Category).filter(Category.name == category)
    if tag:
        query = query.join(post_tags).join(Tag).filter(Tag.name == tag)
    if search:
        search_like = f"%{search}%"
        query = query.filter(
            db.or_(Post.title.ilike(search_like), Post.content.ilike(search_like))
        )
    posts = query.order_by(Post.created_at.desc()).all()
    return jsonify([p.to_dict() for p in posts])

@app.route('/api/posts/<int:post_id>', methods=['GET'])
def get_post(post_id):
    p = Post.query.get_or_404(post_id)
    data = p.to_dict()
    data["comments"] = [c.to_dict() for c in p.comments]
    return jsonify(data)

@app.route('/api/posts', methods=['POST'])
def create_post():
    data = request.get_json()
    title = data.get('title')
    content = data.get('content')
    category_name = data.get('category')
    tag_names = data.get('tags') or []

    category = None
    if category_name:
        category = Category.query.filter_by(name=category_name).first()
        if not category:
            category = Category(name=category_name)
            db.session.add(category)
            db.session.flush()

    p = Post(title=title, content=content, category=category)

    for tname in tag_names:
        tag = Tag.query.filter_by(name=tname).first()
        if not tag:
            tag = Tag(name=tname)
            db.session.add(tag)
            db.session.flush()
        p.tags.append(tag)

    db.session.add(p)
    db.session.commit()
    return jsonify(p.to_dict()), 201

@app.route('/api/posts/<int:post_id>', methods=['DELETE'])
def delete_post(post_id):
    p = Post.query.get_or_404(post_id)
    db.session.delete(p)
    db.session.commit()
    return '', 204


@app.route('/api/posts/<int:post_id>/like', methods=['POST'])
def like_post(post_id):
    p = Post.query.get_or_404(post_id)
    p.likes += 1
    db.session.commit()
    return jsonify({'likes': p.likes})


@app.route('/api/posts/<int:post_id>/comments', methods=['GET', 'POST'])
def post_comments(post_id):
    p = Post.query.get_or_404(post_id)
    if request.method == 'POST':
        data = request.get_json()
        c = Comment(author=data.get('author'), content=data.get('content'), post=p)
        db.session.add(c)
        db.session.commit()
        return jsonify(c.to_dict()), 201
    return jsonify([c.to_dict() for c in p.comments])


@app.route('/api/categories', methods=['GET', 'POST'])
def categories():
    if request.method == 'POST':
        data = request.get_json()
        c = Category(name=data.get('name'))
        db.session.add(c)
        db.session.commit()
        return jsonify(c.to_dict()), 201
    return jsonify([c.to_dict() for c in Category.query.all()])


@app.route('/api/tags', methods=['GET'])
def tags():
    return jsonify([t.to_dict() for t in Tag.query.all()])


@app.route('/api/search')
def search_posts():
    q = request.args.get('q')
    if not q:
        return jsonify([])
    search_like = f"%{q}%"
    posts = (
        Post.query.filter(
            db.or_(Post.title.ilike(search_like), Post.content.ilike(search_like))
        )
        .order_by(Post.created_at.desc())
        .all()
    )
    return jsonify([p.to_dict() for p in posts])


@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'error': 'missing fields'}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'user exists'}), 400
    u = User(username=username, password_hash=generate_password_hash(password))
    db.session.add(u)
    db.session.commit()
    return jsonify({'message': 'registered'})


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    u = User.query.filter_by(username=username).first()
    if not u or not u.check_password(password):
        return jsonify({'error': 'invalid credentials'}), 401
    session['user_id'] = u.id
    return jsonify({'message': 'logged in'})


@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return jsonify({'message': 'logged out'})

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)