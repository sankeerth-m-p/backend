import os
from datetime import timedelta
class Config:
    SQLALCHEMY_DATABASE_URI = "postgresql://dev:Sj69qkprdaY8OO3UIfYXhsMWxAa5wVJ0@dpg-d6c0vt7tn9qs73c8jllg-a.oregon-postgres.render.com/mako_calender_dev"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = "mako_mako_mako"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=7)
    GOOGLE_CLIENT_ID ="661887205849-1vov1od68fokh88qk6d3u30vdo7fhptu.apps.googleusercontent.com"