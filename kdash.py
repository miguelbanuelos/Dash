import pandas as pd
import requests
import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output
import plotly.express as px
import plotly.graph_objects as go
from dash.dash_table.Format import Format, Scheme, Symbol
import dash_bootstrap_components as dbc

# ==============================================================================
# 1. GLOBAL COMPONENTS & CACHE
# ==============================================================================
DATA_CACHE = {}
money_format = Format(precision=2, scheme=Scheme.fixed, symbol=Symbol.yes, symbol_prefix='$', group=True)

# URL fija para evitar que rompa en la lectura del código estructurado
url = 'http://192.168.3.155:3000/run-query'

# ==============================================================================
# 2. DATA FETCHING AND PROCESSING
# ==============================================================================
def get_data(use_cache=False):
    global DATA_CACHE

    if use_cache and DATA_CACHE:
        return (DATA_CACHE.get('Annual'), DATA_CACHE.get('category'),
                DATA_CACHE.get('SKU'), DATA_CACHE.get('df1'),
                DATA_CACHE.get('df3'), DATA_CACHE.get('df2'))

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()
        df = pd.DataFrame(data['results'])
        df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)

        # Annual Aggregation
        Annual = df.groupby(df['Date'].dt.year).agg(
            Orders=('OrderID', 'nunique'),
            Sale=('ProductPrice', 'sum'),
            Net_Profit=('Net_Profit', 'sum'),
            Items=('Qty', 'sum')
        ).reset_index()

        # Category Performance
        category = df.assign(
            OrderCost=df['ProductCost'],
            OrderPrice=df['ProductPrice'],
            Shipping=lambda x: x['shipping_cost'] + x['shipping_tax'],
            ReInvest=lambda x: x['Shipping'] + x['OrderCost']
        )[['Category', 'Qty','Net_Profit', 'ReInvest']].groupby(
            ['Category'], as_index=False).agg('sum').sort_values(by='Net_Profit', ascending=False)

        # SKU Performance
        SKU = df.groupby(['SKU','Category','ProductName'], as_index=False).agg({
            'Qty': 'sum',
            'Net_Profit': 'sum'
        }).sort_values(by='Net_Profit', ascending=False)

        # Order Summary (df1)
        df1 = df.assign(
            Shipping=lambda x: x['shipping_cost'] + x['shipping_tax'],
            OrderTotal=lambda x: x['Shipping'] + x['ProductPrice'],
            ReInvest=lambda x: x['Shipping'] + x['ProductCost'],
        )[['Date', 'OrderID', 'Payment_Type', 'Qty', 'OrderTotal','Commission_Net','ProductPrice',
           'Shipping','ProductCost', 'Net_Profit', 'ReInvest']].groupby(
            ['OrderID','Date','Payment_Type'], as_index=False).agg('sum').sort_values(by='OrderID', ascending=False)
        
        # Monthly Trends (df3)
        df3 = df.assign(
            OrderTotal=lambda x: (x['ProductPrice'] + x['shipping_cost'] + x['shipping_tax'])
        ).groupby(pd.Grouper(key='Date', freq='MS'))[['OrderTotal', 'Net_Profit']].sum().reset_index()

        # Order Details (df2)
        df2 = df.assign(
            Date = df['Date'].dt.strftime('%d-%m-%Y'),
            Price = lambda x: x['ProductNet'].div(x['Qty']).fillna(0),
            Shipping=df['shipping_cost'],
            ShippingTax=df['shipping_tax'],
            TotalTax=lambda x: x['Tax'] + x['ShippingTax'],
            OrderTotal=lambda x: x['TotalTax'] + x['ProductNet'] + x['Shipping'],
        )[['OrderID', 'Date', 'ProductName','SKU','Qty','Price', 'Tax','Shipping','ShippingTax',
           'TotalTax','Commission_Net', 'OrderTotal','Net_Profit']].sort_values(by='OrderID', ascending=False)

        DATA_CACHE = {
            'Annual': Annual, 'category': category, 'SKU': SKU,
            'df1': df1, 'df3': df3, 'df2': df2
        }

        return Annual, category, SKU, df1, df3, df2

    except Exception as e:
        print(f"Error fetching data: {e}")
        empty = pd.DataFrame()
        return empty, empty, empty, empty, empty, empty

# ==============================================================================
# 3. DASH INITIALIZATION & MATERIAL LAYOUT (MOBILE FRIENDLY)
# ==============================================================================
app = dash.Dash(
    __name__, 
    suppress_callback_exceptions=True,
    external_stylesheets=[dbc.themes.FLATLY], # Cambiado a un tema limpio y corporativo
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}]
)

server = app.server

# Barra de navegación responsiva (Se convierte en hamburguesa en móviles automáticamente)
navbar = dbc.NavbarSimple(
    children=[
        dbc.NavItem(dbc.NavLink('Overall', href='/Overall')),
        dbc.NavItem(dbc.NavLink('Order Summary', href='/OrderSummary')),
        dbc.NavItem(dbc.NavLink('Order Details', href='/OrderDetails')),
        dbc.NavItem(dbc.NavLink('Products', href='/Products')),
        dbc.NavItem(dbc.NavLink('Category', href='/Category')),
    ],
    brand="Analytics Dashboard",
    brand_href="/Overall",
    color="primary",
    dark=True,
    className="mb-4",
)

app.layout = html.Div([
    dcc.Location(id='url', refresh=False),
    dcc.Interval(id='interval-component', interval=30 * 1000, n_intervals=0),
    navbar,
    # El contenedor ajusta el ancho de los datos de forma fluida según el dispositivo
    dbc.Container(id='page-content', fluid=True)
])

# ==============================================================================
# 4. UTILITIES
# ==============================================================================
def create_plotly_table(data_frame):
    if data_frame.empty:
        return go.Figure().update_layout(title='No data to display')

    currency_cols = ['Revenue','Price', 'ProductNet', 'Tax', 'Shipping', 'ShippingTax', 'TotalTax', 'Commission_Net', 'Net_Profit',
                     'OrderTotal', 'ProductPrice', 'ProductCost', 'Profit', 'shipping_cost', 'shipping_tax', 'ReInvest', 'Sale']

    formatted_values = []
    for col in data_frame.columns:
        if col in currency_cols:
            formatted_values.append(data_frame[col].apply(lambda x: f"${x:,.2f}"))
        else:
            formatted_values.append(data_frame[col])

    fig = go.Figure(data=[go.Table(
        header=dict(values=list(data_frame.columns), fill_color='#2c3e50', font=dict(color='white', size=13), height=30),
        cells=dict(values=formatted_values, fill_color='#f8f9fa', align='left', font=dict(size=12), height=25)
    )])
    
    # Añadimos margen responsivo a la tabla embebida de plotly
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=450)
    return fig

# ==============================================================================
# 5. ROUTING CALLBACK WITH GRID SYSTEM
# ==============================================================================
@app.callback(
    Output('page-content', 'children'),
    [Input('url', 'pathname'),
     Input('interval-component', 'n_intervals')]
)
def display_page(pathname, n_intervals):
    use_cache = not (n_intervals % 10 == 0 or not DATA_CACHE)
    Annual, category, SKU, df1, df3, df2 = get_data(use_cache=use_cache)

    if df1.empty:
        return dbc.Alert("Error: Could not load data from API.", color="danger", className="m-4")

    # DISEÑO OVERALL
    if pathname == '/Overall' or pathname == '/':
        df3['YearMonth'] = df3['Date'].dt.strftime('%Y-%m')
        fig = px.bar(
            df3, x='YearMonth', y=['OrderTotal', 'Net_Profit'],
            text_auto='.2s', barmode='group',
            labels={'value': 'Amount', 'variable': 'Metric'},
            title='Monthly Order Total vs. Profit'
        )
        fig.update_layout(template="plotly_white", margin=dict(l=10, r=10, t=40, b=10))
        
        return dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody([dcc.Graph(figure=fig)]), className="shadow-sm mb-4"), xs=12),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H4("Annual Summary", className="card-title mb-3"),
                # El Div permite scroll lateral si la tabla no cabe en pantallas xs
                html.Div(dash_table.DataTable(
                    data=Annual.to_dict('records'),
                    columns=[                    
                        {'id': 'Date', 'name': 'Year'},
                        {'id': 'Orders', 'name': 'Total Orders'},
                        {'id': 'Items', 'name': 'Items Sold'},
                        {'id': 'Sale', 'name': 'Total Sale', 'type': 'numeric', 'format': money_format},
                        {'id': 'Net_Profit', 'name': 'Net Revenue', 'type': 'numeric', 'format': money_format}
                    ],
                    style_header={'fontWeight': 'bold', 'backgroundColor': '#f8f9fa'},
                    style_cell={'textAlign': 'left', 'padding': '12px'},
                ), style={"overflowX": "auto"})
            ]), className="shadow-sm mb-4"), xs=12)
        ])

    # DISEÑO ORDER SUMMARY
    elif pathname == '/OrderSummary':
        columns_to_format = ['OrderTotal','ProductPrice','Shipping','ProductCost', 'Net_Profit', 'ReInvest']
        table_columns = [{"name": i, "id": i, "type": "numeric", "format": money_format} if i in columns_to_format
                         else {"name": i, "id": i} for i in df1.columns]
        return dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H2('Order Summary', className="mb-3"),
                html.Div(dash_table.DataTable(
                    data=df1.to_dict('records'), columns=table_columns,
                    page_size=20, sort_action="native", filter_action="native",
                    style_header={'fontWeight': 'bold', 'backgroundColor': '#f8f9fa'},
                    style_cell={'padding': '10px'}
                ), style={"overflowX": "auto"})
            ]), className="shadow-sm mb-4"), xs=12)
        ])

    # DISEÑO ORDER DETAILS
    elif pathname == '/OrderDetails':
        order_ids = sorted(df2['OrderID'].unique(), reverse=True)
        dropdown_options = [{'label': 'ALL Orders', 'value': 'ALL'}] + [{'label': f'Order #{oid}', 'value': oid} for oid in order_ids]

        return dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H2('Order Details', className="mb-3"),
                html.Label("Select Order filter:", className="text-muted mb-2"),
                # Dropdown adaptivo a anchos móviles (100% en xs, máximo 350px en desktop)
                dcc.Dropdown(id='order-dropdown', options=dropdown_options, value='ALL', clearable=False, style={'maxWidth': '350px'}, className="mb-3"),
                html.Div(dcc.Graph(id='order-details-table', figure=create_plotly_table(df2)), style={"overflowX": "auto"})
            ]), className="shadow-sm mb-4"), xs=12)
        ])

    # DISEÑO PRODUCTS
    elif pathname == '/Products':
        return dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H2('Product Performance', className="mb-3"),
                html.Div(dash_table.DataTable(
                    data=SKU.to_dict('records'),
                    columns=[{'id': k, 'name': k, 'type': 'numeric', 'format': money_format} if k == 'Net_Profit' else {'id': k, 'name': k} for k in SKU.columns],
                    page_size=20, sort_action="native", filter_action="native",
                    style_header={'fontWeight': 'bold', 'backgroundColor': '#f8f9fa'},
                    style_cell={'padding': '10px'}
                ), style={"overflowX": "auto"})
            ]), className="shadow-sm mb-4"), xs=12)
        ])

    # DISEÑO CATEGORY
    elif pathname == '/Category':
        return dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H2('Category Performance', className="mb-3"),
                html.Div(dash_table.DataTable(
                    data=category.to_dict('records'),
                    columns=[
                        {'id': 'Category', 'name': 'Category'},
                        {'id': 'Qty', 'name': 'Units Sold'},
                        {'id': 'Net_Profit', 'name': 'Total Profit', 'type': 'numeric', 'format': money_format},
                        {'id': 'ReInvest', 'name': 'ReInvest', 'type': 'numeric', 'format': money_format}
                    ],
                    page_size=20, sort_action="native",
                    style_header={'fontWeight': 'bold', 'backgroundColor': '#f8f9fa'},
                    style_cell={'padding': '10px'}
                ), style={"overflowX": "auto"})
            ]), className="shadow-sm mb-4"), xs=12)
        ])

    return dbc.Container(html.H1("404: Page Not Found", className="text-danger mt-5"))

# ==============================================================================
# 6. INTERACTIVE TABLE CALLBACK
# ==============================================================================
@app.callback(
    Output('order-details-table', 'figure'),
    [Input('order-dropdown', 'value')]
)
def update_table(selected_order_id):
    df2_data = DATA_CACHE.get('df2', pd.DataFrame())
    if df2_data.empty:
        return go.Figure()

    if selected_order_id != 'ALL':
        df2_data = df2_data[df2_data['OrderID'] == selected_order_id]

    return create_plotly_table(df2_data)

# ==============================================================================
# 7. RUN
# ==============================================================================
if __name__ == '__main__':
    get_data() # Initial load
    app.run(debug=True, port=8051)