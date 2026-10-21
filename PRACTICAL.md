# Практическо контролно: Чакалня за игра

## Данни

Нов модел WaitingRoomEntry с OneToOneField към User и created_at. OneToOneField гарантира, че потребител има най-много една заявка.

Добавям color поле в GamePlayer (red, green, blue) за различните цветове при сформиране.

## Допустимост

Потребител е недопустим ако е GamePlayer в игра с status waiting или in_progress. Иначе е допустим.

## Операции

- Записване: проверява дали вече чака (409) и дали е допустим (403), ако не - създава WaitingRoomEntry.
- Отказване: изтрива WaitingRoomEntry ако съществува, иначе не прави нищо.
- Сформиране: задейства се след записване. Ако има >= 3 допустими чакащи, избира 3 случайни, създава Game + 3 GamePlayer с различни цветове и score 0, изтрива избраните от чакалнята. Всичко в transaction.atomic().

## API

- POST /api/waiting-room/join/ - записване
- POST /api/waiting-room/leave/ - отказване
