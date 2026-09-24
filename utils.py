from shared import logger, db


def load_usernames(collection_name):
    """Return the set of lowercased Discord usernames stored in a collection."""
    if db is None:
        logger.error("MongoDB is not available")
        return set()

    try:
        docs = db[collection_name].find(
            {"discord_id": {"$exists": True, "$nin": [None, ""]}},
            {"discord_id": 1},
        )
        usernames = {str(doc["discord_id"]).strip().lower() for doc in docs}
        logger.info(f"Loaded {len(usernames)} usernames from '{collection_name}'")
        return usernames
    except Exception as e:
        logger.error(f"Error loading '{collection_name}' from MongoDB: {e}")
        return set()


def members_by_username(guild):
    """Map lowercased username and display name to member, for fast lookup."""
    lookup = {}
    for member in guild.members:
        if member.bot:
            continue
        lookup.setdefault(member.display_name.lower(), member)
        lookup[member.name.lower()] = member  # real username wins over nicknames
    return lookup
