"""User identity and environment resolution service."""

import logging

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "coddy_user"


class UserService:
    """Manages user identity resolution for ADK sessions and logging."""

    def get_current_user_id(self) -> str:
        """Resolves the current user identity.

        Until user strategy is sorted, it will return a default user identity.

        Returns:
            A clean, non-empty user identifier string.
        """

        return DEFAULT_USER_ID


user_service = UserService()


def get_user_service() -> UserService:
    """Return the UserService singleton.

    Returns:
        UserService singleton.
    """

    return user_service
