from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from .services import (
    join_waiting_room,
    leave_waiting_room,
    AlreadyWaitingError,
    NotEligibleError,
)


class WaitingRoomJoinView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            entry = join_waiting_room(request.user)
        except AlreadyWaitingError:
            return Response(
                {"error": "You are already in the waiting room."},
                status=status.HTTP_409_CONFLICT,
            )
        except NotEligibleError:
            return Response(
                {"error": "You are currently in an active game and cannot join the waiting room."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(
            {"message": "Joined the waiting room.", "created_at": entry.created_at},
            status=status.HTTP_201_CREATED,
        )


class WaitingRoomLeaveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        was_waiting = leave_waiting_room(request.user)
        if was_waiting:
            return Response(
                {"message": "You have left the waiting room."},
                status=status.HTTP_200_OK,
            )
        return Response(
            {"message": "You were not in the waiting room."},
            status=status.HTTP_200_OK,
        )
