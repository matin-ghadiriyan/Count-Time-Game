from .login_register import LoginRegister
from .dashboard_and_room import DashboardAndRoom
from .leaderboard_and_History import LeaderboardAndHistory
from .API import API
from .home import Index


def blueprints():
    return [
        LoginRegister,
        DashboardAndRoom,
        LeaderboardAndHistory,
        API,
        Index,
    ]