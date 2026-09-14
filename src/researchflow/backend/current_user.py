from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status


def get_current_user_id(
    user_id: Annotated[
        UUID | None,
        Header(alias="X-ResearchFlow-User-Id"),
    ] = None,
) -> UUID:
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user_id


CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]
