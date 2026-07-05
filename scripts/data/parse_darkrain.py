import requests
from bs4 import BeautifulSoup
import json
import re
from urllib.parse import urljoin

def parse_site(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    result = {
        'url': url,
        'status_code': response.status_code,
        'main_blocks': {},
        'dom_structure': {},
        'product_images': []
    }

    css_classes = {
        'header': set(),
        'product_card': set(),
        'button': set(),
        'other': set()
    }

    header_selectors = ['header', '[class*="header"]', '[class*="nav"]', '[class*="menu"]', '[id*="header"]', '[id*="nav"]']
    product_card_selectors = ['[class*="product"]', '[class*="card"]', '[class*="item"]', '[class*="goods"]', '[class*="shop"]']
    button_selectors = ['button', '[class*="button"]', '[class*="btn"]', '[class*="submit"]', 'a[class*="btn"]', 'a[class*="button"]']

    for selector in header_selectors:
        for elem in soup.select(selector):
            classes = elem.get('class', [])
            css_classes['header'].update(classes)

    for selector in product_card_selectors:
        for elem in soup.select(selector):
            classes = elem.get('class', [])
            css_classes['product_card'].update(classes)

    for selector in button_selectors:
        for elem in soup.select(selector):
            classes = elem.get('class', [])
            css_classes['button'].update(classes)

    for tag in soup.find_all():
        classes = tag.get('class', [])
        if classes:
            is_header = any(c in css_classes['header'] for c in classes)
            is_product = any(c in css_classes['product_card'] for c in classes)
            is_button = any(c in css_classes['button'] for c in classes)

            if not (is_header or is_product or is_button):
                for cls in classes:
                    if cls not in css_classes['header'] and cls not in css_classes['product_card'] and cls not in css_classes['button']:
                        css_classes['other'].add(cls)

    result['main_blocks'] = {
        'header': sorted(list(css_classes['header'])),
        'product_card': sorted(list(css_classes['product_card'])),
        'button': sorted(list(css_classes['button'])),
        'other_classes': sorted(list(css_classes['other']))
    }

    def get_dom_tree(element, max_depth=6, current_depth=0):
        if current_depth >= max_depth:
            return {'tag': element.name, 'truncated': True}

        node = {'tag': element.name}

        if element.name in ['img', 'br', 'hr', 'input', 'meta', 'link']:
            return node

        attributes = {}
        if element.get('class'):
            attributes['class'] = element.get('class')
        if element.get('id'):
            attributes['id'] = element.get('id')
        if element.get('href'):
            attributes['href'] = element.get('href')
        if element.get('src'):
            attributes['src'] = element.get('src')

        if attributes:
            node['attributes'] = attributes

        children = []
        for child in element.children:
            if child.name:
                child_tree = get_dom_tree(child, max_depth, current_depth + 1)
                children.append(child_tree)

        if children:
            node['children'] = children

        return node

    html_tag = soup.find('html')
    if html_tag:
        result['dom_structure'] = get_dom_tree(html_tag)

    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src') or img.get('data-lazy-src') or img.get('data-original')
        if src:
            full_url = urljoin(url, src)
            alt = img.get('alt', '')
            result['product_images'].append({
                'url': full_url,
                'alt': alt,
                'source_tag': 'img'
            })

    product_links = soup.find_all('a', href=True)
    for link in product_links:
        href = link.get('href')
        if href and ('product' in href.lower() or 'item' in href.lower() or '/p/' in href):
            full_url = urljoin(url, href)
            text = link.get_text(strip=True)[:100]
            result['product_images'].append({
                'url': full_url,
                'text': text,
                'source_tag': 'a'
            })

    seen = set()
    unique_images = []
    for img in result['product_images']:
        if img['url'] not in seen:
            seen.add(img['url'])
            unique_images.append(img)
    result['product_images'] = unique_images

    return result

if __name__ == '__main__':
    url = 'https://darkrain.store/'
    try:
        data = parse_site(url)
        with open('darkrain_parse_result.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f'Parsing complete! Saved to darkrain_parse_result.json')
        print(f'Found {len(data["main_blocks"]["header"])} header classes')
        print(f'Found {len(data["main_blocks"]["product_card"])} product card classes')
        print(f'Found {len(data["main_blocks"]["button"])} button classes')
        print(f'Found {len(data["product_images"])} image/product links')
    except Exception as e:
        print(f'Error: {e}')