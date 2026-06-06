"""
Flask API 服务器 — 为前端仪表板提供数据
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
import json
import csv
import subprocess

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)


@app.route('/')
def index():
    return send_from_directory('../frontend', 'index.html')


@app.route('/api/status')
def status():
    """系统状态"""
    data_dir = 'data'
    return jsonify({
        'raw_data_exists': os.path.exists(f'{data_dir}/raw_toys.csv'),
        'processed_data_exists': os.path.exists(f'{data_dir}/processed_toys.csv'),
        'report_exists': os.path.exists(f'{data_dir}/toy_selection.xlsx'),
    })


@app.route('/api/products')
def get_products():
    """获取处理后的产品列表"""
    csv_path = 'data/processed_toys.csv'
    if not os.path.exists(csv_path):
        return jsonify({'error': '请先生成数据', 'products': []})
    
    products = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 转换数值字段
            numeric_fields = ['price', 'rating', 'review_count', 'sales_est', 'competitors',
                            'estimated_profit_margin', 'net_profit', 'total_fba_cost',
                            'total_score', 'weight_lbs', 'margin_score', 'sales_score',
                            'review_score', 'rating_score', 'comp_score']
            for k in numeric_fields:
                if k in row and row[k]:
                    try:
                        row[k] = float(row[k])
                    except:
                        pass
            products.append(row)
    
    # 按评分排序
    products.sort(key=lambda x: float(x.get('total_score', 0)), reverse=True)
    
    return jsonify({'products': products, 'total': len(products)})


@app.route('/api/recommendations')
def get_recommendations():
    """获取选品推荐 (筛选后的)"""
    csv_path = 'data/processed_toys.csv'
    if not os.path.exists(csv_path):
        return jsonify({'error': '请先生成数据', 'recommendations': []})
    
    # 从 Excel 读取推荐（如果有的话），否则实时筛选
    config_path = 'config.json'
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    filters = config['filters']
    products = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            price = float(row['price'])
            rating = float(row['rating'])
            reviews = int(row['review_count'])
            sales = int(row['sales_est'])
            comp = int(row['competitors'])
            margin = float(row['estimated_profit_margin'])
            weight = float(row['weight_lbs'])
            
            if (filters['price_min'] <= price <= filters['price_max'] and
                rating >= filters['min_rating'] and
                reviews >= filters['min_reviews'] and
                sales >= filters['min_sales_est'] and
                comp <= filters['max_competitors'] and
                margin >= filters['min_profit_margin'] and
                weight <= filters['weight_max_lbs']):
                products.append(row)
    
    # 简易评分
    for p in products:
        margin = float(p['estimated_profit_margin'])
        sales = float(p['sales_est'])
        rating = float(p['rating'])
        reviews = float(p['review_count'])
        comp = float(p['competitors'])
        comp_score = max(0, 100 - (comp * 100 / max(1, sales)))
        total = (margin*200*0.35 + min(sales/3000,1)*100*0.25 + min(reviews/1000,1)*100*0.15 + rating/5*100*0.15 + comp_score*0.10)
        p['total_score'] = round(total, 1)
        p['recommendation'] = '⭐ 强烈推荐' if total >= 75 else ('👍 推荐' if total >= 55 else '👀 可考虑')
    
    products.sort(key=lambda x: x['total_score'], reverse=True)
    return jsonify({'recommendations': products, 'total': len(products)})


@app.route('/api/stats')
def get_stats():
    """统计数据"""
    csv_path = 'data/processed_toys.csv'
    if not os.path.exists(csv_path):
        return jsonify({'error': '请先生成数据'})
    
    products = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            products.append(row)
    
    prices = [float(p['price']) for p in products]
    margins = [float(p['estimated_profit_margin']) for p in products]
    ratings = [float(p['rating']) for p in products]
    
    # 子类目分布
    cats = {}
    for p in products:
        cat = p.get('subcategory', 'Other')
        cats[cat] = cats.get(cat, 0) + 1
    
    # 利润区间分布
    profit_brackets = {'<15%': 0, '15-25%': 0, '25-35%': 0, '35-45%': 0, '>45%': 0}
    for m in margins:
        if m < 0.15: profit_brackets['<15%'] += 1
        elif m < 0.25: profit_brackets['15-25%'] += 1
        elif m < 0.35: profit_brackets['25-35%'] += 1
        elif m < 0.45: profit_brackets['35-45%'] += 1
        else: profit_brackets['>45%'] += 1
    
    return jsonify({
        'total_products': len(products),
        'avg_price': round(sum(prices)/len(prices), 2),
        'avg_margin': round(sum(margins)/len(margins)*100, 1),
        'avg_rating': round(sum(ratings)/len(ratings), 1),
        'category_distribution': cats,
        'profit_brackets': profit_brackets,
        'price_range': [min(prices), max(prices)],
    })


@app.route('/api/run_pipeline', methods=['POST'])
def run_pipeline():
    """运行完整数据管道"""
    try:
        from collector import collect_toy_data, save_raw_data
        from processor import process_products
        from selector import select_products
        
        # Step 1: 采集
        data = collect_toy_data(150)
        save_raw_data(data)
        
        # Step 2: 处理
        process_products()
        
        # Step 3: 选品
        recommendations = select_products()
        
        return jsonify({
            'success': True,
            'message': f'管道完成！采集 {len(data)} 条 → 推荐 {len(recommendations)} 款产品',
            'total_collected': len(data),
            'total_recommended': len(recommendations),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/export')
def export_report():
    """下载 Excel 报告"""
    excel_path = 'data/toy_selection.xlsx'
    if os.path.exists(excel_path):
        return send_from_directory('data', 'toy_selection.xlsx', as_attachment=True)
    return jsonify({'error': '报告尚未生成，请先运行管道'}), 404


if __name__ == '__main__':
    print("🚀 亚马逊玩具选品系统 API 启动...")
    print("   📡 http://localhost:3000")
    app.run(host='0.0.0.0', port=3000, debug=True)
