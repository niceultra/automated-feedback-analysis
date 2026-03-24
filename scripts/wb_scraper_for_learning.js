(async function() {
    const SCAN_TIME_LIMIT = 30000; // 30 секунд прокрутки
    console.log(`🚀 Начинаю чистую прокрутку без ответов продавца (${SCAN_TIME_LIMIT/1000}с)...`);

    const autoScroll = async () => {
        return new Promise((resolve) => {
            let totalHeight = 0;
            let distance = 500;
            let startTime = Date.now();
            let timer = setInterval(() => {
                let scrollHeight = document.body.scrollHeight;
                window.scrollBy(0, distance);
                totalHeight += distance;
                if (totalHeight >= scrollHeight || (Date.now() - startTime) >= SCAN_TIME_LIMIT) {
                    clearInterval(timer);
                    resolve();
                }
            }, 200);
        });
    };

    await autoScroll();

    const reviewCards = document.querySelectorAll('.comments__item.feedback');
    const results = [];
    results.push(['Рейтинг', 'Статус выкупа', 'Достоинства', 'Недостатки', 'Комментарий'].join(';'));

    reviewCards.forEach(card => {
        // 1. Рейтинг покупателя
        const ratingElement = card.querySelector('.feedback__rating');
        let rating = '5';
        if (ratingElement) {
            const starClass = Array.from(ratingElement.classList).find(c => /^star\d+$/.test(c));
            if (starClass) rating = starClass.replace('star', '');
        }

        // 2. Статус выкупа
        const purchased = card.querySelector('.feedback__state--text')?.innerText.trim() || 'Нет данных';

        // --- КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: Ищем только внутри контента отзыва, игнорируя ответ продавца ---
        // Берем только тот блок, который НЕ является ответом продавца
        const buyerContent = card.querySelector('.feedback__content');

        if (!buyerContent) return; // Если контента нет вообще

        const pros = buyerContent.querySelector('.feedback__text--item-pro')?.innerText.replace('Достоинства:', '').trim() || '';
        const cons = buyerContent.querySelector('.feedback__text--item-con')?.innerText.replace('Недостатки:', '').trim() || '';

        // Собираем основной комментарий, исключая блоки Pro и Con
        const textItems = buyerContent.querySelectorAll('.feedback__text--item');
        let commentParts = [];
        textItems.forEach(item => {
            if (!item.classList.contains('feedback__text--item-pro') && !item.classList.contains('feedback__text--item-con')) {
                commentParts.push(item.innerText.replace('Комментарий:', '').trim());
            }
        });

        let comment = commentParts.join(' ').trim();

        // Если через специальные айтемы не нашлось, берем текст самого параграфа в блоке покупателя
        if (!comment) {
            const mainText = buyerContent.querySelector('.j-feedback__text');
            if (mainText) {
                // Клонируем ноду, чтобы удалить из нее вложенные про/кон и не испортить страницу
                const tempNode = mainText.cloneNode(true);
                tempNode.querySelectorAll('.feedback__text--item-pro, .feedback__text--item-con').forEach(el => el.remove());
                comment = tempNode.innerText.trim();
            }
        }

        // Пропускаем, если покупатель ничего не написал (ни плюсов, ни минусов, ни текста)
        if (!pros && !cons && !comment) return;

        const clean = (text) => `"${text.replace(/"/g, '""').replace(/;/g, ',').replace(/\n/g, ' ')}"`;

        results.push([rating, clean(purchased), clean(pros), clean(cons), clean(comment)].join(';'));
    });

    const csvContent = "\uFEFF" + results.join("\n");
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `wb_reviews_clean_${Math.floor(Date.now()/1000)}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    console.log(`📊 Готово! Собрано информативных отзывов: ${results.length - 1}`);
})();