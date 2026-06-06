"""使用 curl_cffi 采集亚马逊真实产品数据 - 修复版"""
import sys, io
if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except (ValueError, AttributeError):
        pass

from curl_cffi import requests as curl_requests
from bs4 import BeautifulSoup
import re
import pandas as pd
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

def extract_price(item):
    """提取价格，处理多种货币和格式"""
    price_selectors = [
        '.a-price .a-offscreen',
        'span.a-price[data-a-size="xl"] .a-offscreen',
        'span.a-price[data-a-size="l"] .a-offscreen',
        '.a-price .a-price-whole',
    ]
    
    for sel in price_selectors:
        el = item.select_one(sel)
        if not el:
            continue
        
        if 'a-offscreen' in sel:
            text = el.get('innerHTML', '') or el.text or ''
            text = text.replace('&nbsp;', ' ').strip()
            # 去除货币符号 (CNY, $, £, €, ¥ 等)
            text_clean = re.sub(r'[A-Za-z€£¥\s]+', '', text)
            match = re.search(r'([\d,.]+)', text_clean)
            if match:
                price = float(match.group(1).replace(',', ''))
                # 检测货币并转换为 USD
                raw = text.upper()
                if 'CNY' in raw or '¥' in raw:
                    price = price / 7.2  # CNY → USD
                elif '£' in raw or 'GBP' in raw:
                    price = price * 1.27
                elif '€' in raw or 'EUR' in raw:
                    price = price * 1.08
                # 如果是 JPY 需要特殊处理（日元太大）
                if price > 5000 and ('JPY' in raw or '¥' in raw):
                    price = price / 150  # JPY → USD
                return round(price, 2)
        else:
            # .a-price-whole approach
            whole = el.text.strip().replace(',', '')
            frac_el = item.select_one('.a-price-fraction')
            frac = frac_el.text.strip() if frac_el else '00'
            try:
                return round(float(f"{whole}.{frac}"), 2)
            except:
                pass
    
    return None

def extract_rating(item):
    """提取评分"""
    for sel in ['.a-icon-star-small .a-icon-alt', '.a-icon-alt', '.a-icon-star .a-icon-alt']:
        el = item.select_one(sel)
        if el:
            text = el.text.strip() if hasattr(el, 'text') else str(el)
            match = re.search(r'([\d.]+)\s*out', text)
            if match:
                return float(match.group(1))
    return None

def extract_reviews(item):
    """提取评论数，处理 K/M 缩写"""
    # 优先找 ratings-count 组件
    for el in item.select('[data-csa-c-content-id="alf-customer-ratings-count-component"]'):
        text = el.text.strip()
        text = text.strip('()')
        if 'K' in text.upper():
            num = float(text.upper().replace('K', '').strip())
            return int(num * 1000)
        elif 'M' in text.upper():
            num = float(text.upper().replace('M', '').strip())
            return int(num * 1000000)
        else:
            nums = re.findall(r'[\d,]+', text)
            if nums:
                return int(nums[0].replace(',', ''))
    
    # 回退：扫描所有文本
    text = item.get_text()
    # 找类似 "16K ratings" 或 "3,200 reviews"
    for pattern in [r'\(([\d.]+[Kk])\)', r'([\d,]+)\s*(?:ratings?|reviews?)',
                    r'([\d.]+[Kk])\s*(?:ratings?|reviews?)']:
        match = re.search(pattern, text)
        if match:
            val = match.group(1)
            if 'K' in val.upper():
                return int(float(val.upper().replace('K', '')) * 1000)
            elif 'M' in val.upper():
                return int(float(val.upper().replace('M', '')) * 1000000)
            else:
                return int(val.replace(',', ''))
    return 0

def scrape_category(keyword):
    """快速刮取单页"""
    products = []
    url = f"https://www.amazon.com/s?k={keyword}&i=toys-and-games&page=1"
    try:
        resp = curl_requests.get(url, impersonate="chrome131", timeout=15,
            headers={"Accept-Language": "en-US,en;q=0.9"})
        
        if resp.status_code != 200:
            return products
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        items = soup.select('[data-component-type="s-search-result"]')
        
        for item in items:
            try:
                asin = item.get('data-asin', '')
                if not asin or len(asin) < 10:
                    continue
                
                title_el = item.select_one('h2 a span')
                if not title_el:
                    continue
                title = title_el.text.strip()
                
                price = extract_price(item)
                rating = extract_rating(item)
                reviews = extract_reviews(item)
                
                # 合理的玩具价格范围（USD）
                if title and price and 5.0 < price < 150.0:
                    products.append({
                        'asin': asin,
                        'title': title[:250],
                        'price': price,
                        'rating': rating or 0,
                        'review_count': reviews,
                        'category': 'Toys & Games',
                        'subcategory': keyword.replace('+', ' ').title(),
                    })
            except:
                continue
    except Exception as e:
        pass
    
    return products

# 并发刮取多个类目
categories = [
    "STEM+toys",
    "building+blocks",
    "board+games+family", 
    "action+figures",
    "dolls+toys",
    "outdoor+toys",
    "educational+toys",
    "puzzle+toys",
    "remote+control+car",
    "arts+crafts+kids",
    "plush+toys",
    "sensory+toys",
]

print("=== Amazon Real Product Collector (fixed) ===\n")

all_products = []
seen_asins = set()

with ThreadPoolExecutor(max_workers=4) as executor:
    futures = {executor.submit(scrape_category, cat): cat for cat in categories}
    for future in as_completed(futures):
        cat = futures[future]
        try:
            products = future.result(timeout=20)
            new = 0
            for p in products:
                if p['asin'] not in seen_asins:
                    seen_asins.add(p['asin'])
                    all_products.append(p)
                    new += 1
            print(f"  [OK] {cat}: {new} new (page had {len(products)}) | total={len(all_products)}")
        except Exception as e:
            print(f"  [FAIL] {cat}: {e}")

os.makedirs('G:/agent/projects/amazon-toy-selector/data', exist_ok=True)
df = pd.DataFrame(all_products)
df.to_csv('G:/agent/projects/amazon-toy-selector/data/raw_products.csv', index=False, encoding='utf-8')

print(f"\n=== Collection Complete: {len(all_products)} products ===")
if len(all_products) > 0:
    print(f"Price: ${df['price'].min():.2f} - ${df['price'].max():.2f}")
    print(f"Rating: {df['rating'].min():.1f} - {df['rating'].max():.1f}")
    print(f"Reviews: {df['review_count'].min()} - {df['review_count'].max()}")
    print("\n[Top 10]:")
    for i, (_, r) in enumerate(df.head(10).iterrows()):
        print(f"  {i+1}. [{r['asin']}] {r['title'][:70]} | ${r['price']:.2f} | *{r['rating']} | {r['review_count']}rev")
