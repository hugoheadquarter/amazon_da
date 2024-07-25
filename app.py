import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import re
from dateutil import parser

# Set page config
st.set_page_config(page_title="Amazon Product Analysis Dashboard", layout="wide")

# Database connection
@st.cache_resource
def get_connection():
    try:
        db_path = 'amazon_products.db'
        return sqlite3.connect(db_path, check_same_thread=False)
    except sqlite3.Error as e:
        st.error(f"An error occurred while connecting to the database: {e}")
        return None

conn = get_connection()

# Data loading functions
@st.cache_data
def load_product_data():
    if conn is None:
        return pd.DataFrame()
    try:
        query = """
        SELECT p.*, c.name as category_name
        FROM products p
        JOIN product_categories pc ON p.id = pc.product_id
        JOIN categories c ON pc.category_id = c.id
        """
        df = pd.read_sql_query(query, conn)
        return df
    except pd.io.sql.DatabaseError as e:
        st.error(f"An error occurred while loading product data: {e}")
        return pd.DataFrame()

@st.cache_data
def load_review_data():
    if conn is None:
        return pd.DataFrame()
    try:
        query = """
        SELECT r.*, p.id as product_id, c.name as category_name
        FROM reviews r
        JOIN products p ON r.product_id = p.id
        JOIN product_categories pc ON p.id = pc.product_id
        JOIN categories c ON pc.category_id = c.id
        """
        return pd.read_sql_query(query, conn)
    except pd.io.sql.DatabaseError as e:
        st.error(f"An error occurred while loading review data: {e}")
        return pd.DataFrame()

# Data processing functions
@st.cache_data
def process_product_data(df):
    if df.empty:
        return df
    df['review_count'] = df['review_count'].fillna(0).astype(int)
    
    def extract_price(price_str):
        if pd.isna(price_str):
            return None
        match = re.search(r'\$?([\d,]+\.?\d*)', str(price_str))
        if match:
            return float(match.group(1).replace(',', ''))
        return None

    df['price'] = df['price'].apply(extract_price)
    return df

@st.cache_data
def process_review_data(df):
    if df.empty:
        return df
    df['sentiment'] = df['rating'].apply(lambda x: 'Positive' if x >= 4 else ('Negative' if x <= 2 else 'Neutral'))
    
    def parse_date(date_string):
        try:
            date_part = date_string.split('on')[1].split(',')[0].strip() + date_string.split(',')[1]
            return parser.parse(date_part)
        except:
            return pd.NaT

    df['date'] = df['date'].apply(parse_date)
    return df

# Load and process data
product_df = process_product_data(load_product_data())
review_df = process_review_data(load_review_data())

if product_df.empty or review_df.empty:
    st.error("Failed to load data. Please check your database connection and try again.")
    st.stop()

# Ensure review_df has a unique index
review_df = review_df.reset_index(drop=True)

# Check for and rename duplicate columns
def rename_duplicate_columns(df):
    cols = pd.Series(df.columns)
    for dup in cols[cols.duplicated()].unique(): 
        cols[cols[cols == dup].index.values.tolist()] = [dup + '_' + str(i) if i != 0 else dup for i in range(sum(cols == dup))]
    df.columns = cols
    return df

review_df = rename_duplicate_columns(review_df)
product_df = rename_duplicate_columns(product_df)

# Sidebar for global filters
st.sidebar.title("Filters")
selected_categories = st.sidebar.multiselect("Categories", ['All Categories'] + list(product_df['category_name'].unique()), default=['All Categories'])
min_price, max_price = st.sidebar.slider("Price Range", 
                                         float(product_df['price'].min()), 
                                         float(product_df['price'].max()), 
                                         (float(product_df['price'].min()), float(product_df['price'].max())))

# Apply filters
def filter_dataframe(df):
    filtered = df[
        (df['price'] >= min_price) &
        (df['price'] <= max_price)
    ]

    if 'All Categories' not in selected_categories:
        filtered = filtered[filtered['category_name'].isin(selected_categories)]
    
    return filtered

filtered_product_df = filter_dataframe(product_df)

# Filter review_df based on the filtered product IDs
filtered_review_df = pd.merge(review_df, filtered_product_df[['id']], left_on='product_id', right_on='id', how='inner', suffixes=('', '_product'))

# If category filter is applied, ensure reviews match the selected categories
if 'All Categories' not in selected_categories:
    filtered_review_df = filtered_review_df[filtered_review_df['category_name'].isin(selected_categories)]

def executive_dashboard():
    st.title("Executive Dashboard")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Products", f"{len(filtered_product_df):,}")
    col2.metric("Avg. Product Price", f"${filtered_product_df['price'].mean():.2f}")
    col3.metric("Total Reviews (with comments)", f"{len(filtered_review_df):,}")
    col4.metric("Avg. Customer Rating", f"{filtered_review_df['rating'].mean():.2f}")
    
    fig = px.histogram(filtered_product_df, x="price", nbins=50, title="Price Distribution")
    fig.update_layout(xaxis_title="Price ($)", yaxis_title="Count")
    st.plotly_chart(fig, use_container_width=True)
    
    top_categories = filtered_product_df['category_name'].value_counts().head(3)
    fig = px.bar(x=top_categories.index, y=top_categories.values, title="Top Categories by Product Count")
    fig.update_layout(xaxis_title="Category", yaxis_title="Number of Products")
    st.plotly_chart(fig, use_container_width=True)

def product_performance():
    st.title("Product Performance Analysis")
    
    st.subheader("Top Products")
    most_reviewed = filtered_product_df.sort_values('review_count', ascending=False).head(10)
    st.dataframe(most_reviewed[['title', 'price', 'rating', 'review_count', 'category_name']])
    
    fig = px.scatter(filtered_product_df, x='price', y='rating', color='category_name', 
                     title="Price vs. Rating by Category", hover_data=['title'])
    fig.update_layout(xaxis_title="Price ($)", yaxis_title="Rating")
    st.plotly_chart(fig, use_container_width=True)

def category_insights():
    st.title("Category Insights")
    
    # Category Statistics
    category_stats = filtered_product_df.groupby('category_name').agg({
        'price': ['mean', 'min', 'max'],
        'rating': 'mean',
        'review_count': 'sum'
    }).reset_index()
    category_stats.columns = ['Category', 'Avg Price', 'Min Price', 'Max Price', 'Avg Rating', 'Total Reviews']
    st.dataframe(category_stats)
    
    # Category Comparison
    fig = px.scatter(category_stats, x='Avg Price', y='Avg Rating', size='Total Reviews', 
                     color='Category', hover_name='Category',
                     title="Category Comparison: Price vs. Rating vs. Review Volume")
    fig.update_layout(xaxis_title="Average Price ($)", yaxis_title="Average Rating")
    st.plotly_chart(fig, use_container_width=True)

    # Top products for each category
    st.subheader("Top Products by Category (Based on Number of Reviews)")
    
    for category in filtered_product_df['category_name'].unique():
        st.write(f"**{category}**")
        top_products = filtered_product_df[filtered_product_df['category_name'] == category].nlargest(3, 'review_count')
        
        for _, product in top_products.iterrows():
            with st.container():
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                col1.write(product['title'])
                col2.write(f"Price: ${product['price']:.2f}")
                col3.write(f"Rating: {product['rating']:.1f}")
                col4.write(f"Reviews: {product['review_count']}")
        
        st.write("---")  # Add a separator between categories

def customer_behavior():
    st.title("Customer Behavior Analysis")
    
    sentiment_counts = filtered_review_df['sentiment'].value_counts()
    fig = px.pie(values=sentiment_counts.values, names=sentiment_counts.index, title="Review Sentiment Distribution")
    st.plotly_chart(fig, use_container_width=True)
    
    rating_counts = filtered_review_df['rating'].value_counts().sort_index()
    fig = px.bar(x=rating_counts.index, y=rating_counts.values, title="Rating Distribution")
    fig.update_layout(xaxis_title="Rating", yaxis_title="Number of Reviews")
    st.plotly_chart(fig, use_container_width=True)

def pricing_analysis():
    st.title("Pricing Analysis")
    
    fig = px.box(filtered_product_df, x="category_name", y="price", title="Price Distribution by Category")
    fig.update_layout(xaxis_title="Category", yaxis_title="Price ($)")
    st.plotly_chart(fig, use_container_width=True)
    
    fig = px.scatter(filtered_product_df, x="price", y="review_count", color="category_name", 
                     title="Price vs. Review Count", hover_data=['title'])
    fig.update_layout(xaxis_title="Price ($)", yaxis_title="Number of Reviews")
    st.plotly_chart(fig, use_container_width=True)

# Main app logic
def main():
    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to", ["Executive Dashboard", "Product Performance", "Category Insights", 
                                      "Customer Behavior", "Pricing Analysis"])

    try:
        if page == "Executive Dashboard":
            executive_dashboard()
        elif page == "Product Performance":
            product_performance()
        elif page == "Category Insights":
            category_insights()
        elif page == "Customer Behavior":
            customer_behavior()
        elif page == "Pricing Analysis":
            pricing_analysis()
    except Exception as e:
        st.error(f"An error occurred while rendering the {page} page: {e}")

    # Add explanation and developer info at the bottom of the sidebar
    st.sidebar.markdown("---")
    st.sidebar.info(
        "This app provides insights into Amazon summer product data, "
        "including pricing, ratings, and customer reviews.\n\n"
        "Developed by Dylan Kim"
    )

if __name__ == "__main__":
    main()
