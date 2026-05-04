(async function() {
    // 1. СПИСОК ССЫЛОК
    const productLinks = [
        "https://www.wildberries.ru/catalog/684264302/feedbacks?imtId=1123914487&size=923730142",
        "https://www.wildberries.ru/catalog/175573791/feedbacks?imtId=160382659&size=290962656",
        "https://www.wildberries.ru/catalog/165879171/feedbacks?imtId=152015978&size=276156190"
    ];

    const MIN_TEXT_LENGTH = 20;
    const allResults = [];
    allResults.push(['nmId', 'rating', 'text'].join(';'));

    // Резервная функция (на случай, если в ссылке нет imtId)
    async function getProductMetadata(nmId) {
        try {
            // Используем официальный API
            const url = `https://card.wb.ru/cards/v1/detail?appType=1&curr=rub&dest=-1257786&nm=${nmId}`;
            const res = await fetch(url);
            if (!res.ok) return null;
            const json = await res.json();
            return json.data.products[0]?.imtId || null;
        } catch (e) {
            return null;
        }
    }

    console.log(`🚀 Начинаю работу. Всего ссылок: ${productLinks.length}`);

    for (let link of productLinks) {
        // 1. Извлекаем nmId (артикул)
        const nmIdMatch = link.match(/catalog\/(\d+)/);
        const nmId = nmIdMatch ? nmIdMatch[1] : "unknown";

        // 2. Извлекаем imtId напрямую из ссылки
        const imtIdMatch = link.match(/imtId=(\d+)/);
        let imtId = imtIdMatch ? imtIdMatch[1] : null;

        console.log(`📡 Обработка артикула ${nmId}...`);

        // 3. Если в ссылке imtId не нашли, пробуем через API
        if (!imtId) {
            console.log(`🔍 imtId не найден в ссылке, запрашиваю у API...`);
            imtId = await getProductMetadata(nmId);
        }

        if (!imtId) {
            console.error(`❌ Ошибка: не удалось определить ID модели (imtId) для ${nmId}. Пропускаю.`);
            continue;
        }

        console.log(`✅ ID модели найден: ${imtId}. Собираю отзывы...`);

        try {

            const response = await fetch(`https://feedbacks1.wb.ru/feedbacks/v1/${imtId}`);

            if (!response.ok) {
                console.error(`❌ Сервер отзывов недоступен для ${nmId} (Status: ${response.status})`);
                continue;
            }

            const data = await response.json();
            const reviews = data.feedbacks || [];
            let count = 0;

            reviews.forEach(r => {
                const rating = r.productValuation || '5';
                const pros = (r.pros || '').trim();
                const cons = (r.cons || '').trim();
                const comment = (r.text || '').trim();

                let fullText = [pros, cons, comment].filter(t => t.length > 0).join(' ');

                if (fullText.length < MIN_TEXT_LENGTH) return;

                // Очистка текста от кавычек и точек с запятой для корректного CSV
                const clean = (text) => `"${text.replace(/"/g, '""').replace(/;/g, ',').replace(/\n/g, ' ')}"`;

                allResults.push([
                    nmId,
                    rating,
                    clean(fullText)
                ].join(';'));
                count++;
            });

            console.log(`🎉 Готово! Для ${nmId} собрано ${count} отзывов.`);
            await new Promise(r => setTimeout(r, 800)); // Пауза

        } catch (e) {
            console.error(`❌ Ошибка при загрузке отзывов для ${nmId}:`, e);
        }
    }

    // 2. СКАЧИВАНИЕ
    if (allResults.length > 1) {
        const csvContent = "\uFEFF" + allResults.join("\n");
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `wb_reviews_${Date.now()}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        console.log("💾 Файл скачан!");
    } else {
        console.warn("⚠️ Отзывы не найдены. Возможно, стоит проверить ссылки или попробовать позже.");
    }
})();