from flask import render_template , Blueprint , redirect , url_for
from flask_login import current_user

Index = Blueprint("Index", __name__)

# ----------------------------------------------------------------
# Landing
# ----------------------------------------------------------------
@Index.route("/")
def index():
    """Landing page: If the user is logged in, redirect to the dashboard, otherwise Landing."""
    if current_user.is_authenticated:
        return redirect(url_for("pages.dashboard"))
    return render_template("index.html")
