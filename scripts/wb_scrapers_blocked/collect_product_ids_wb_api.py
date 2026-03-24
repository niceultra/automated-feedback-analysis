import datetime
import requests
import json
from retry import retry


def get_catalogs_wb() -> dict:
    url = 'https://static-basket-01.wbbasket.ru/vol0/data/main-menu-ru-ru-v3.json'
    headers = {'Accept': '*/*', 'User-Agent': 'Mozilla/5.0'}
    return requests.get(url, headers=headers).json()


def get_data_category(catalogs_wb: dict) -> list:
    catalog_data = []
    if isinstance(catalogs_wb, dict) and 'childs' not in catalogs_wb:
        catalog_data.append({
            'name': catalogs_wb['name'],
            'shard': catalogs_wb.get('shard'),
            'url': catalogs_wb['url'],
            'query': catalogs_wb.get('query')
        })
    elif isinstance(catalogs_wb, dict):
        catalog_data.append({
            'name': catalogs_wb['name'],
            'shard': catalogs_wb.get('shard'),
            'url': catalogs_wb['url'],
            'query': catalogs_wb.get('query')
        })
        catalog_data.extend(get_data_category(catalogs_wb['childs']))
    else:
        for child in catalogs_wb:
            catalog_data.extend(get_data_category(child))
    return catalog_data


def search_category_in_catalog(url: str, catalog_list: list) -> dict:
    for catalog in catalog_list:
        if catalog['url'] == url.split('https://www.wildberries.ru')[-1]:
            print(f'найдено совпадение: {catalog["name"]}')
            return catalog


def get_data_from_json(json_file: dict) -> list:
    data_list = []
    for data in json_file['data']['products']:
        data_list.append({
            'id': data.get('id'),
            'name': data.get('name'),
            'price': int(data.get("priceU") / 100),
            'salePriceU': int(data.get('salePriceU') / 100),
            'cashback': data.get('feedbackPoints'),
            'sale': data.get('sale'),
            'brand': data.get('brand'),
            'rating': data.get('rating'),
            'supplier': data.get('supplier'),
            'supplierRating': data.get('supplierRating'),
            'feedbacks': data.get('feedbacks'),
            'reviewRating': data.get('reviewRating'),
            'promoTextCard': data.get('promoTextCard'),
            'promoTextCat': data.get('promoTextCat'),
            'link': f'https://www.wildberries.ru/catalog/{data.get("id")}/detail.aspx'
        })
    return data_list


@retry(Exception, tries=5, delay=1)
def scrap_page(page: int, shard: str, query: str, discount: int = None) -> dict:
    headers = {"User-Agent": "Mozilla/5.0"}

    url = f'https://catalog.wb.ru/catalog/{shard}/catalog?' \
          f'appType=1&curr=rub' \
          f'&dest=-1257786' \
          f'&locale=ru' \
          f'&page={page}' \
          f'&sort=popular&spp=0' \
          f'&{query}' \
          f'&discount={discount}'

    r = requests.get(url, headers=headers)
    print(f'Статус: {r.status_code} Страница {page}')
    return r.json()


def save_json(data: list, filename: str):
    with open(f'{filename}.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f'Сохранено в {filename}.json')


def parser(url: str, discount: int = 0):
    catalog_data = get_data_category(get_catalogs_wb())

    try:
        category = search_category_in_catalog(url=url, catalog_list=catalog_data)

        data_list = []

        for page in range(1, 51):
            data = scrap_page(
                page=page,
                shard=category['shard'],
                query=category['query'],
                discount=discount
            )

            items = get_data_from_json(data)
            print(f'Добавлено: {len(items)}')

            if items:
                data_list.extend(items)
            else:
                break

        print(f'Собрано всего: {len(data_list)} товаров')

        save_json(data_list, category["name"])

    except Exception as e:
        print("Ошибка:", e)


if __name__ == '__main__':
    while True:
        url = input('Введите ссылку категории (или q): ')
        if url == 'q':
            break

        discount = int(input('Минимальная скидка (0 если не нужна): '))

        parser(url=url, discount=discount)