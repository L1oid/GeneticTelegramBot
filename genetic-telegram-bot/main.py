import requests
import emoji
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, CallbackContext

TOKEN = 'TOKEN_BOT'
API_URL = 'http://genetic.kemsu.ru/api/questionnaires'
QUESTION_URL = 'http://genetic.kemsu.ru/api/questionnaires/questions'
ANSWERS_URL = 'http://genetic.kemsu.ru/api/questionnaires/questions/answers-to-choose'
SUBMISSION_URL = 'http://genetic.kemsu.ru/api/questionnaires/submissions'
PAGE_SIZE = 6


async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text('Здравствуйте! Здесь вы можете пройти анкетирование связанное с генетическими вопросами.')
    context.user_data['page'] = 1
    await get_questionnaires(update, context)


async def get_questionnaires(update: Update, context: CallbackContext, title: str = '', page: int = 1, retry: bool = False) -> None:
    params = {'page': page, 'pageSize': PAGE_SIZE}
    if title:
        params['title'] = title
    response = requests.get(API_URL, params=params)
    if response.status_code == 200:
        questionnaires = response.json()
        if questionnaires:
            keyboard = [
                [InlineKeyboardButton(q['title'], callback_data=f"select_{q['id']}")]
                for q in questionnaires
            ]
            nav_buttons = []
            if page > 1:
                nav_buttons.append(InlineKeyboardButton('⬅️', callback_data='prev_page'))
            if len(questionnaires) == PAGE_SIZE:
                nav_buttons.append(InlineKeyboardButton('➡️', callback_data='next_page'))
            if nav_buttons:
                keyboard.append(nav_buttons)
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text('Выберите анкету:', reply_markup=reply_markup)
        else:
            if title and not retry:
                await update.message.reply_text('Анкеты с таким названием не найдены. Вывожу стандартный список.')
                await get_questionnaires(update, context)
            else:
                await update.message.reply_text('Анкеты не найдены.')
    elif response.status_code == 404:
        if title and not retry:
            await update.message.reply_text('Анкеты с таким названием не найдены. Вывожу стандартный список.')
            await get_questionnaires(update, context)
        else:
            await update.message.reply_text('Анкеты не найдены.')
    else:
        await update.message.reply_text('Ошибка получения анкет.')


async def get_questions(update: Update, context: CallbackContext, questionnaire_id: int) -> None:
    response = requests.get(f"{QUESTION_URL}?questionnaireId={questionnaire_id}")
    if response.status_code == 200:
        questions = response.json()
        questions.sort(key=lambda q: q['questionNumber'])  # Sort questions by questionNumber
        context.user_data['questions'] = questions
        context.user_data['current_question'] = 0
        context.user_data['answers'] = []
        context.user_data['questionnaire_id'] = questionnaire_id
        await ask_question(update, context)
    else:
        await update.message.reply_text('Ошибка получения вопросов анкеты.')


async def ask_question(update: Update, context: CallbackContext) -> None:
    questions = context.user_data.get('questions', [])
    current_question_index = context.user_data.get('current_question', 0)

    if current_question_index < len(questions):
        question = questions[current_question_index]
        context.user_data['current_question_id'] = question['questionId']
        question_text = f"Вопрос № {question['questionNumber']}: {question['questionText']}"
        additional_info = ""

        if question['questionType'] == 'select':
            additional_info = "Выберите один из предложенных вариантов ответа:"
        elif question['questionType'] == 'free':
            additional_info = "Введите ваш ответ в поле ниже:"

        question_text_with_info = f"{question_text}\n\n{additional_info}"

        if question['answerRequired']:
            skip_button = InlineKeyboardButton('❗Обязательный вопрос', callback_data='ignore')
        else:
            skip_button = InlineKeyboardButton('⏭️ Пропустить вопрос', callback_data='skip_question')

        cancel_button = InlineKeyboardButton('❌ Отменить прохождение', callback_data='cancel_survey')

        if question.get('questionType') == 'select':
            response = requests.get(f"{ANSWERS_URL}?questionId={question['questionId']}")
            if response.status_code == 200:
                answers = response.json()
                keyboard = [[InlineKeyboardButton(f"{index + 1}. {ans['text']}", callback_data=f"answer_{ans['text']}")]
                            for index, ans in enumerate(answers)]
                if skip_button:
                    keyboard.append([skip_button])
                keyboard.append([cancel_button])
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(question_text_with_info, reply_markup=reply_markup)
            else:
                await update.message.reply_text('Ошибка получения ответов.')
        else:
            context.user_data['waiting_for_answer'] = True
            keyboard = []
            if skip_button:
                keyboard.append([skip_button])
            keyboard.append([cancel_button])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(question_text_with_info, reply_markup=reply_markup)
    else:
        await submit_answers(update, context)


async def handle_answer(update: Update, context: CallbackContext, answer_text: str = None) -> None:
    current_question_index = context.user_data.get('current_question', 0)
    questions = context.user_data.get('questions', [])

    if current_question_index < len(questions):
        question = questions[current_question_index]
        if answer_text is not None:
            context.user_data['answers'].append({'questionId': question['questionId'], 'answerText': answer_text})

        context.user_data['current_question'] += 1
        context.user_data['waiting_for_answer'] = False
        await ask_question(update, context)
    else:
        await submit_answers(update, context)


async def submit_answers(update: Update, context: CallbackContext) -> None:
    questionnaire_id = context.user_data['questionnaire_id']
    answers = context.user_data['answers']
    solve = {'questionnaireId': questionnaire_id, 'answerSet': answers}
    response = requests.post(SUBMISSION_URL, json=solve)
    if response.status_code == 200:
        await update.message.reply_text("Результат прохождения: \n\n" + response.text)
        await get_questionnaires(update, context)
    else:
        await update.message.reply_text('Ошибка при отправке анкеты.')
        await get_questionnaires(update, context)


async def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    if query:
        await query.answer()
        if query.data.startswith('select_'):
            questionnaire_id = int(query.data.split('_')[1])
            await get_questions(query, context, questionnaire_id)
        elif query.data.startswith('answer_'):
            answer_text = query.data.split('_')[1]
            await handle_answer(query, context, answer_text)
        elif query.data == 'prev_page':
            context.user_data['page'] = max(1, context.user_data.get('page', 1) - 1)
            await get_questionnaires(query, context, page=context.user_data['page'])
        elif query.data == 'next_page':
            context.user_data['page'] = context.user_data.get('page', 1) + 1
            await get_questionnaires(query, context, page=context.user_data['page'])
        elif query.data == 'skip_question':
            await handle_answer(query, context, answer_text=None)
        elif query.data == 'ignore':
            await query.answer()
        elif query.data == 'cancel_survey':
            context.user_data.clear()
            await get_questionnaires(query, context)


def contains_emoji(text: str) -> bool:
    return any(char in emoji.EMOJI_DATA for char in text)


async def search(update: Update, context: CallbackContext) -> None:
    if contains_emoji(update.message.text):
        return

    current_question_index = context.user_data.get('current_question', 0)
    questions = context.user_data.get('questions', [])

    if current_question_index < len(questions):
        question = questions[current_question_index]
        if question.get('questionType') == 'select':
            await update.message.reply_text('Пожалуйста, выберите один из предложенных вариантов ответа.')
            return

    if context.user_data.get('waiting_for_answer', False):
        await handle_answer(update, context, update.message.text)
    else:
        query = update.message.text
        context.user_data['page'] = 1
        await get_questionnaires(update, context, title=query)


def main() -> None:
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(
        filters.TEXT &
        ~filters.COMMAND &
        ~filters.PHOTO &
        ~filters.VIDEO &
        ~filters.ANIMATION,
        search))

    app.run_polling()


if __name__ == '__main__':
    main()
