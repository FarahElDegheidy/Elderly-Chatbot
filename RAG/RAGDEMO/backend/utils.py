from passlib.context import CryptContext
from db import db
from typing import List, Dict, Optional
from datetime import datetime, UTC

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

async def update_user_field(email: str, field: str, updated_list: list):
    if field not in ["likes", "dislikes", "allergies"]:
        raise ValueError("Invalid field")

    await db.users.update_one(
        {"email": email},
        {"$set": {field: updated_list}}
    )


async def save_chat_log(email: str, chat: list):
    await db.chat_logs.insert_one({
        "email": email,
        "chat": chat,
        "timestamp": datetime.now(UTC)
    })

async def get_user_chats(email: str):
    chats = await db.chat_logs.find({"email": email}).sort("timestamp", -1).to_list(length=20)
    return [{"_id": str(chat["_id"]), "chat": chat["chat"], "timestamp": chat["timestamp"]} for chat in chats]

async def get_user_by_email(email: str):
    return await db.users.find_one({"email": email})

async def create_user(data: dict):
    data["password"] = hash_password(data["password"])
    result = await db.users.insert_one(data)
    return str(result.inserted_id)

async def get_user_favourites_by_email(email: str) -> Optional[List[Dict]]:
    user = await get_user_by_email(email)
    if user and "favorite_recipes" in user:
        return user["favorite_recipes"]
    return None


async def add_recipe_to_favourites(user_email: str, recipe_title: str, recipe_content: str):
    user = await get_user_by_email(user_email)
    if not user:
        return {"status": "error", "message": "User not found."}

    favourites = user.get("favorite_recipes", [])
    for recipe in favourites:
        if recipe["title"] == recipe_title:
            return {"status": "exists", "message": "Recipe already in favourites."}

    new_entry = {"title": recipe_title, "recipe": recipe_content}
    await db.users.update_one(
        {"email": user_email},
        {"$push": {"favorite_recipes": new_entry}}
    )
    return {"status": "success", "message": "Recipe added to favourites."}
