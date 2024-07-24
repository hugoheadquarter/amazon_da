# Amazon Product Analysis Dashboard

## Overview
This Streamlit application provides an interactive dashboard for analyzing Amazon product data. It offers insights into product pricing, ratings, customer reviews, and category performance.

## Features
- Executive Dashboard: Overview of key metrics and top categories
- Product Performance: Analysis of top-rated and most reviewed products
- Category Insights: Detailed statistics and top products for each category
- Customer Behavior: Review sentiment analysis and rating distribution
- Pricing Analysis: Price distribution and correlation with review counts

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/amazon-product-analysis.git
   cd amazon-product-analysis
   ```

2. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

3. Ensure you have the SQLite database file (`amazon_products.db`) in the correct location:
   ```
   /Users/dylankim/Desktop/resume/amazon/db/amazon_products.db
   ```

## Usage

Run the Streamlit app:
```
streamlit run app.py
```

Navigate to the local URL provided by Streamlit (typically `http://localhost:8501`).

## Data
The app uses a SQLite database containing Amazon product and review data. The database should include the following tables:
- products
- reviews
- categories
- product_categories

## Filters
Users can filter the data by:
- Category
- Price range

## Pages
1. Executive Dashboard
2. Product Performance
3. Category Insights
4. Customer Behavior
5. Pricing Analysis

## Development
This app was developed using Streamlit, Pandas, and Plotly. It uses SQLite for data storage and retrieval.

## Author
Developed by Dylan Kim
